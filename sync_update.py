"""Sync billing status → render tagihan.html dari template + git push

Semua periode & tanggal dihitung OTOMATIS dari tanggal sistem.
Periode billing: 16-ke-16. Jatuh tempo selalu tanggal 16.

Usage:
  python sync_update.py lunas    # Tandai LUNAS + git push
  python sync_update.py belum    # Tandai BELUM + git push
  python sync_update.py refresh  # Refresh periode saja (tanpa ubah status)
  python sync_update.py show     # Tampilkan status tanpa push
"""

import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
TEMPLATE = REPO_DIR / "template.html"
HTML_FILE = REPO_DIR / "tagihan.html"
# Git credential disimpan via: git config --local credential.helper store

# ── Indonesian month names ──
BLN_ID = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
          "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

# Billing mulai Juni 2026 (bulan pertama)
BILLING_START = (6, 2026)  # (month, year)


def compute_period():
    """Hitung periode billing 16-ke-16 berdasarkan tanggal hari ini."""
    today = datetime.now()
    if today.day >= 16:
        start_m, start_y = today.month, today.year
        end_m = today.month + 1
        end_y = today.year
        if end_m > 12:
            end_m = 1
            end_y += 1
    else:
        end_m, end_y = today.month, today.year
        start_m = today.month - 1
        start_y = today.year
        if start_m < 1:
            start_m = 12
            start_y -= 1

    due_date = f"16 {BLN_ID[end_m]} {end_y}"
    period_range = f"16 {BLN_ID[start_m]} – 16 {BLN_ID[end_m]} {end_y}"
    period_label = f"{BLN_ID[end_m]} {end_y}"

    next_end_m = end_m + 1
    next_end_y = end_y
    if next_end_m > 12:
        next_end_m = 1
        next_end_y += 1
    next_due = f"16 {BLN_ID[next_end_m]} {next_end_y}"

    # ISO timestamp for JS countdown (16th of end_month, 00:00 WIB = UTC+7)
    due_ts = datetime(end_y, end_m, 16, 0, 0, 0).isoformat() + "+07:00"

    return {
        "period_range": period_range,
        "due_date": due_date,
        "period_label": period_label,
        "next_due": next_due,
        "end_month": BLN_ID[end_m],
        "end_year": end_y,
        "due_timestamp": due_ts,
        "end_month_num": end_m,
    }


def read_current_status():
    """Baca status dari tagihan.html yang sudah ada (atau default 'belum')."""
    if not HTML_FILE.exists():
        return "belum"
    text = HTML_FILE.read_text(encoding="utf-8")
    m = re.search(r'class="badge (lunas|belum)"', text)
    return m.group(1) if m else "belum"


def month_before(m_idx, y):
    """Return (month_idx, year) for previous month."""
    m = m_idx - 1
    if m < 1:
        return 12, y - 1
    return m, y


def generate_history_rows(period_info):
    """Generate riwayat dari bulan pertama billing sampai sekarang."""
    end_m_idx = BLN_ID.index(period_info["end_month"])
    end_y = period_info["end_year"]
    start_m, start_y = BILLING_START

    # Build status map from existing file
    status_map = {}
    if HTML_FILE.exists():
        text = HTML_FILE.read_text(encoding="utf-8")
        for match in re.finditer(
            r'<td>(\w+) (\d{4})</td>\s*<td class="(status-\w+)">([^<]+)</td>',
            text, re.DOTALL
        ):
            status_map[(match.group(1), int(match.group(2)))] = (match.group(3), match.group(4).strip())

    rows = []
    m_idx, y = end_m_idx, end_y

    while True:
        month_name = BLN_ID[m_idx]
        due = f"16 {month_name} {y}"
        key = (month_name, y)

        # Stop if we went before billing start
        if y < start_y or (y == start_y and m_idx < start_m):
            break

        if key == (period_info["end_month"], period_info["end_year"]):
            # Current period — follow badge status
            current = read_current_status()
            cls = f"status-{current}"
            txt = "✅ LUNAS" if current == "lunas" else "❌ BELUM"
        elif key in status_map:
            cls, txt = status_map[key]
        else:
            cls = "status-lunas"
            txt = "✅ LUNAS"

        rows.append(
            f'        <tr>\n'
            f'          <td>{month_name} {y}</td>\n'
            f'          <td class="{cls}">{txt}</td>\n'
            f'          <td>{due}</td>\n'
            f'        </tr>'
        )

        m_idx, y = month_before(m_idx, y)

    return "\n".join(rows)


def build_alert_html(status, period_info):
    if status == "lunas":
        return (
            f'  <div class="alert info">\n'
            f'    <span class="icon">✅</span>\n'
            f'    <div>\n'
            f'      <strong>Pembayaran LUNAS ✅</strong><br>\n'
            f'      Akses internet aktif. Tagihan berikutnya: {period_info["next_due"]}.\n'
            f'    </div>\n'
            f'  </div>'
        )
    else:
        return (
            f'  <div class="alert warn">\n'
            f'    <span class="icon">⚠️</span>\n'
            f'    <div>\n'
            f'      <strong>Jatuh tempo: {period_info["due_date"]}</strong><br>\n'
            f'      Akses internet otomatis diputus jika belum lunas setelah tanggal 16.\n'
            f'    </div>\n'
            f'  </div>'
        )


def build_description(status, period_info):
    if status == "lunas":
        return (
            f'      ✅ Pembayaran telah diterima.\n'
            f'      Akses internet tetap aktif hingga periode berikutnya.'
        )
    else:
        return (
            f'      Segera lakukan pembayaran sebelum '
            f'<strong style="color:var(--text)">{period_info["due_date"]}</strong>.\n'
            f'      Pengingat otomatis dikirim via Telegram H-2 dan H-1.'
        )


def build_qris_section():
    """Generate QRIS section — image if available, otherwise instructions."""
    qris_img = REPO_DIR / "qris.png"
    if qris_img.exists():
        return (
            f'    <div style="text-align:center;margin-top:12px;padding:16px;'
            f'background:white;border-radius:12px">\n'
            f'      <img src="qris.png" alt="QRIS" style="max-width:200px;height:auto">\n'
            f'      <p style="color:#333;font-size:0.8rem;margin-top:8px">'
            f'Scan dengan GoPay/DANA/OVO/m-Banking</p>\n'
            f'    </div>'
        )
    else:
        return (
            f'    <div style="text-align:center;margin-top:12px;padding:16px;'
            f'background:rgba(245,158,11,0.06);border:1px dashed var(--amber);'
            f'border-radius:8px">\n'
            f'      <p style="color:var(--amber);font-size:0.85rem">'
            f'📱 QRIS belum tersedia — minta QR code ke pemilik</p>\n'
            f'    </div>'
        )


def render(status):
    """Render template → tagihan.html."""
    template = TEMPLATE.read_text(encoding="utf-8")
    info = compute_period()
    now = datetime.now().strftime("%d %b %Y, %H:%M WIB")

    en_months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    id_months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
                 "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    for en, id_ in zip(en_months, id_months):
        now = now.replace(en, id_)

    replacements = {
        "{{ PERIOD_RANGE }}": info["period_range"],
        "{{ DUE_DATE }}": info["due_date"],
        "{{ PERIOD_LABEL }}": info["period_label"],
        "{{ STATUS_CLASS }}": status,
        "{{ STATUS_TEXT }}": "LUNAS" if status == "lunas" else "BELUM LUNAS",
        "{{ ALERT_HTML }}": build_alert_html(status, info),
        "{{ DESCRIPTION_HTML }}": build_description(status, info),
        "{{ HISTORY_ROWS }}": generate_history_rows(info),
        "{{ UPDATE_TIME }}": now,
        "{{ DUE_TIMESTAMP }}": info["due_timestamp"],
        "{{ QRIS_SECTION }}": build_qris_section(),
    }

    html = template
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)

    HTML_FILE.write_text(html, encoding="utf-8")
    print(f"✅ Rendered: status={status.upper()}, periode={info['period_range']}")
    print(f"   Due: {info['due_date']}")


def git_push():
    """Commit and push (auth via git credential helper)."""
    r = subprocess.run(["git", "add", "tagihan.html", "template.html", "qris.png"],
                       cwd=str(REPO_DIR), capture_output=True, text=True, timeout=10)
    r = subprocess.run(["git", "commit", "-m", f"Auto: update tagihan"],
                       cwd=str(REPO_DIR), capture_output=True, text=True, timeout=10)
    r = subprocess.run(["git", "push", "origin", "main"],
                       cwd=str(REPO_DIR), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        print(f"git push error: {r.stderr.strip()}")
        return False
    print("✅ Git push berhasil")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "show":
        info = compute_period()
        status = read_current_status()
        print(f"Status: {status.upper()}")
        print(f"Periode: {info['period_range']}")
        print(f"Jatuh tempo: {info['due_date']}")
    elif cmd in ("lunas", "belum"):
        render(cmd)
        git_push()
    elif cmd == "refresh":
        status = read_current_status()
        render(status)
        git_push()
    else:
        print(f"ERROR: {cmd} — pakai: lunas | belum | refresh | show")
        sys.exit(1)
