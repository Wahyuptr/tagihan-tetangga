"""Sync billing status → render tagihan.html dari template + git push

Semua periode & tanggal dihitung OTOMATIS dari tanggal sistem.
Periode billing: 16-ke-16. Batas bayar tanggal 15 (router memutus mulai tgl 16 00:00).
Kunci periode = bulan AKHIR periode, sama dengan tag router: periode 16 Sep–16 Okt 2026
= "2026-10" = komentar PPPoE LUNAS-10-2026.

Data (siapa lunas kapan, tarif, kontak) disimpan sebagai JSON di dalam tagihan.html
(<script id="billing-data">). Halaman menghitung periode & status sendiri di browser,
jadi tetap benar walau tidak dirender ulang saat periode berganti.

Usage:
  python sync_update.py lunas    # Lunasi periode tertunggak paling awal (atau periode berjalan) + git push
  python sync_update.py belum    # Batalkan lunas periode berjalan + git push
  python sync_update.py batal 2026-11  # Batalkan lunas periode tertentu (tombol "Batalkan" QRIS otomatis)
  python sync_update.py refresh  # Render ulang (status dari data) + push kalau ada perubahan
  python sync_update.py show     # Tampilkan status tanpa push
"""

import json
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
TEMPLATE = REPO_DIR / "template.html"
HTML_FILE = REPO_DIR / "tagihan.html"

BLN_ID = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
          "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

DUE_DAY = 16
BILLING_START = (6, 2026)  # (month, year) — bulan pertama tagihan

# Nilai awal kalau tagihan.html belum punya blok data (migrasi dari versi lama).
DEFAULT_DATA = {
    "customer": "Pak Radjamalik",
    "amount": 150000,
    "speed_max": 30,
    "speed_min": 10,
    "due_day": DUE_DAY,
    "billing_start": f"{BILLING_START[1]}-{BILLING_START[0]:02d}",
    "wa_owner": "6281386341923",
    "tg_owner": "whayuptr",
    "paid": {},
}
DATA_RE = re.compile(r'<script id="billing-data" type="application/json">(.*?)</script>', re.S)


def compute_period(today=None):
    """Hitung periode billing 16-ke-16 berdasarkan tanggal hari ini."""
    today = today or datetime.now()
    if today.day >= DUE_DAY:
        start_m, start_y = today.month, today.year
        end_m, end_y = today.month + 1, today.year
        if end_m > 12:
            end_m, end_y = 1, end_y + 1
    else:
        end_m, end_y = today.month, today.year
        start_m, start_y = today.month - 1, today.year
        if start_m < 1:
            start_m, start_y = 12, start_y - 1

    return {
        "period_range": f"{DUE_DAY} {BLN_ID[start_m]} – {DUE_DAY} {BLN_ID[end_m]} {end_y}",
        "due_date": f"{DUE_DAY - 1} {BLN_ID[end_m]} {end_y}",
        "period_label": f"{BLN_ID[end_m]} {end_y}",
        "key": f"{end_y}-{end_m:02d}",
        "end_month": BLN_ID[end_m],
        "end_year": end_y,
        "end_month_num": end_m,
    }


def period_keys(upto_key):
    """Semua kunci periode dari BILLING_START sampai upto_key (urut lama → baru)."""
    y, m = BILLING_START[1], BILLING_START[0]
    out = []
    while f"{y}-{m:02d}" <= upto_key:
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _legacy_paid(text):
    """Baca tabel riwayat format lama (<td>Oktober 2026</td><td class="status-lunas">)."""
    paid = {}
    for mo, yr, cls in re.findall(r'<td>(\w+) (\d{4})</td>\s*<td class="status-(\w+)">', text):
        if mo in BLN_ID and cls == "lunas":
            paid[f"{yr}-{BLN_ID.index(mo):02d}"] = ""
    return paid


def load_data():
    data = json.loads(json.dumps(DEFAULT_DATA))
    if HTML_FILE.exists():
        text = HTML_FILE.read_text(encoding="utf-8")
        m = DATA_RE.search(text)
        if m:
            data.update(json.loads(m.group(1)))
        else:
            data["paid"] = _legacy_paid(text)
    return data


def read_current_status():
    """Status periode berjalan (dihitung dari data, bukan dari badge lama)."""
    data = load_data()
    return "lunas" if compute_period()["key"] in data["paid"] else "belum"


def rp(n):
    return "Rp " + f"{int(n):,}".replace(",", ".")


def fmt_date(iso):
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return f"{d} {BLN_ID[m]} {y}"
    except (ValueError, AttributeError):
        return "—"


def generate_history_rows(data, info):
    """Baris riwayat untuk tampilan tanpa JavaScript (JS menggambar ulang di browser)."""
    rows = []
    for key in reversed(period_keys(info["key"])):
        y, m = key.split("-")
        if key in data["paid"]:
            cls, txt, when = "lunas", "LUNAS", fmt_date(data["paid"][key]) if data["paid"][key] else "—"
        else:
            cls, txt, when = "belum", "BELUM", ""
        rows.append(f'        <tr><td>{BLN_ID[int(m)]} {y}</td><td>{when}</td>'
                    f'<td class="status-{cls}"><span class="tag {cls}">{txt}</span></td></tr>')
    return "\n".join(rows)


def build_qris_section():
    if (REPO_DIR / "qris.png").exists():
        return ('    <div class="qris">\n'
                '      <img src="qris.png" alt="QRIS pembayaran" loading="lazy">\n'
                '      <p>Scan pakai GoPay, DANA, OVO, ShopeePay atau m-Banking</p>\n'
                '      <a class="btn ghost" style="margin-top:10px" href="qris.png" download="QRIS-internet.png">⬇️ Simpan gambar QRIS</a>\n'
                '    </div>')
    return ('    <div class="qris"><p>📱 QRIS belum tersedia — minta kode QR ke pemilik jaringan.</p></div>')


def status_message(status, info):
    if status == "lunas":
        return f"✅ Terima kasih! Tagihan <b>{info['period_label']}</b> sudah lunas."
    return (f"Bayar paling lambat <b>{info['due_date']}</b> pukul 23:59 WIB. "
            f"Lewat dari itu internet diputus otomatis.")


def render(data, now=None):
    """Render template → tagihan.html. Kembalikan status periode berjalan."""
    now = now or datetime.now()
    info = compute_period(now)
    status = "lunas" if info["key"] in data["paid"] else "belum"
    upd = now.strftime("%d %b %Y, %H:%M WIB")
    for en, id_ in zip(["May", "Aug", "Oct", "Dec"], ["Mei", "Agu", "Okt", "Des"]):
        upd = upd.replace(en, id_)
    data["updated"] = now.strftime("%Y-%m-%dT%H:%M:%S+07:00")

    blob = json.dumps(data, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    repl = {
        "{{ CUSTOMER }}": data["customer"],
        "{{ STATUS_CLASS }}": status,
        "{{ STATUS_TEXT }}": "LUNAS" if status == "lunas" else "BELUM DIBAYAR",
        "{{ STATUS_MESSAGE }}": status_message(status, info),
        "{{ PERIOD_RANGE }}": info["period_range"],
        "{{ PERIOD_LABEL }}": info["period_label"],
        "{{ DUE_DATE }}": info["due_date"],
        "{{ AMOUNT }}": rp(data["amount"]),
        "{{ AMOUNT_RAW }}": str(int(data["amount"])),
        "{{ SPEED_MAX }}": str(data["speed_max"]),
        "{{ SPEED_MIN }}": str(data["speed_min"]),
        "{{ WA_OWNER }}": data["wa_owner"],
        "{{ TG_OWNER }}": data["tg_owner"],
        "{{ HISTORY_ROWS }}": generate_history_rows(data, info),
        "{{ QRIS_SECTION }}": build_qris_section(),
        "{{ UPDATE_TIME }}": upd,
        "{{ BILLING_DATA }}": blob,
    }
    html = TEMPLATE.read_text(encoding="utf-8")
    for k, v in repl.items():
        html = html.replace(k, v)
    left = re.findall(r"\{\{ [A-Z_]+ \}\}", html)
    if left:
        raise RuntimeError(f"placeholder belum terisi: {sorted(set(left))}")
    HTML_FILE.write_text(html, encoding="utf-8")
    print(f"✅ Rendered: status={status.upper()}, periode={info['period_range']} ({info['key']})")
    return status


def mark_lunas(data, today=None):
    """Lunasi tunggakan paling awal; kalau tidak ada tunggakan, periode berjalan."""
    today = today or datetime.now()
    info = compute_period(today)
    for key in period_keys(info["key"]):
        if key not in data["paid"]:
            data["paid"][key] = today.strftime("%Y-%m-%d")
            return key
    return None


def mark_belum(data, today=None):
    key = compute_period(today)["key"]
    return key if data["paid"].pop(key, None) is not None else None


def mark_batal(data, key):
    """Batalkan lunas periode `key` (YYYY-MM). Kembalikan key kalau tadinya lunas."""
    if not re.fullmatch(r"\d{4}-\d{2}", str(key or "")):
        raise ValueError(f"kunci periode tidak valid: {key!r}")
    return key if data["paid"].pop(key, None) is not None else None


def git_push(msg="Auto: update tagihan"):
    """Commit and push (auth via SSH key). Tidak commit kalau tidak ada perubahan."""
    sp = subprocess
    sp.run(["git", "add", "tagihan.html", "template.html", "qris.png", "sync_update.py"],
           cwd=str(REPO_DIR), capture_output=True, text=True, timeout=10)
    if sp.run(["git", "diff", "--cached", "--quiet"], cwd=str(REPO_DIR)).returncode == 0:
        print("ℹ️ Tidak ada perubahan untuk di-push")
        return True
    sp.run(["git", "commit", "-m", msg], cwd=str(REPO_DIR), capture_output=True, text=True, timeout=10)
    r = sp.run(["git", "push", "origin", "main"], cwd=str(REPO_DIR), capture_output=True, text=True, timeout=30)
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
    data = load_data()
    if cmd == "show":
        info = compute_period()
        print(f"Status: {read_current_status().upper()}")
        print(f"Periode: {info['period_range']} ({info['key']})")
        print(f"Batas bayar: {info['due_date']}")
        print(f"Lunas: {', '.join(sorted(data['paid'])) or '-'}")
    elif cmd == "lunas":
        key = mark_lunas(data)
        print(f"LUNAS untuk periode {key}" if key else "Semua periode sudah lunas — tidak ada yang diubah")
        render(data)
        git_push()
    elif cmd == "belum":
        key = mark_belum(data)
        print(f"Batal lunas periode {key}" if key else "Periode berjalan memang belum lunas")
        render(data)
        git_push()
    elif cmd == "batal":
        key = mark_batal(data, sys.argv[2] if len(sys.argv) > 2 else "")
        print(f"Batal lunas periode {key}" if key else "Periode itu memang belum lunas")
        render(data)
        git_push()
    elif cmd == "refresh":
        render(data)
        git_push()
    else:
        print(f"ERROR: {cmd} — pakai: lunas | belum | batal YYYY-MM | refresh | show")
        sys.exit(1)
