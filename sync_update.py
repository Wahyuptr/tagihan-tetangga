"""Sync billing status → update tagihan.html + git push ke GitHub Pages

Usage:
  python sync_update.py lunas    # Tandai LUNAS, git push
  python sync_update.py belum    # Tandai BELUM, git push
  python sync_update.py show     # Tampilkan status saat ini tanpa push
"""

import re
import sys
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
HTML_FILE = REPO_DIR / "tagihan.html"
TOKEN = "***"  # ghp_CX...


def git(*args):
    """Run git command in repo dir, return (returncode, stdout)."""
    r = subprocess.run(
        ["git"] + list(args),
        cwd=str(REPO_DIR),
        capture_output=True,
        text=True,
        timeout=30
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def show_status():
    text = HTML_FILE.read_text(encoding="utf-8")
    m = re.search(r'class="badge (lunas|belum)"', text)
    if m:
        print(f"Status: {m.group(1).upper()}")
    else:
        print("Status: tidak ditemukan")


def set_status(status: str):
    if status not in ("lunas", "belum"):
        print(f"ERROR: status harus 'lunas' atau 'belum'")
        sys.exit(1)

    text = HTML_FILE.read_text(encoding="utf-8")
    current = re.search(r'class="badge (lunas|belum)"', text)
    old_status = current.group(1) if current else None

    if not old_status:
        print("ERROR: badge tidak ditemukan")
        sys.exit(1)

    if old_status == status:
        print(f"Status sudah {status.upper()}, skip.")
        return

    # ── 1. Badge class + text ──
    text = re.sub(r'class="badge (lunas|belum)"', f'class="badge {status}"', text)
    text = re.sub(
        r'<span class="dot"></span> (LUNAS|BELUM LUNAS)',
        f'<span class="dot"></span> {"LUNAS" if status == "lunas" else "BELUM LUNAS"}',
        text
    )

    # ── 2. Alert section ──
    if status == "lunas":
        text = text.replace(
            '  <div class="alert warn">\n    <span class="icon">⚠️</span>\n    <div>\n      <strong>Jatuh tempo: 16',
            '  <div class="alert info">\n    <span class="icon">✅</span>\n    <div>\n      <strong>Pembayaran LUNAS ✅</strong><br>\n      Akses internet aktif. Tagihan berikutnya: 16'
        )
    else:
        text = re.sub(
            r'<div class="alert info">\n\s+<span class="icon">.*?</span>\n\s+<div>\n\s+<strong>Pembayaran LUNAS.*?</strong><br>\n\s+Akses internet aktif\. Tagihan berikutnya: 16.*?</div>',
            '  <div class="alert warn">\n    <span class="icon">⚠️</span>\n    <div>\n      <strong>Jatuh tempo: 16 Juni 2026</strong><br>\n      Akses internet otomatis diputus jika belum lunas setelah tanggal 16.\n    </div>',
            text,
            flags=re.DOTALL
        )

    # ── 3. Description text ──
    if status == "lunas":
        text = re.sub(
            r'<p style="margin-top:12px;font-size:0\.88rem;color:var\(--muted\)">\n\s+Segera lakukan pembayaran.*?</p>',
            '<p style="margin-top:12px;font-size:0.88rem;color:var(--muted)">\n      ✅ Pembayaran telah diterima.\n      Akses internet tetap aktif hingga periode berikutnya.\n    </p>',
            text,
            flags=re.DOTALL
        )
    else:
        text = re.sub(
            r'<p style="margin-top:12px;font-size:0\.88rem;color:var\(--muted\)">\n\s+✅ Pembayaran.*?</p>',
            '<p style="margin-top:12px;font-size:0.88rem;color:var(--muted)">\n      Segera lakukan pembayaran sebelum <strong style="color:var(--text)">16 Juni 2026</strong>.\n      Pengingat otomatis dikirim via Telegram H-2 dan H-1.\n    </p>',
            text,
            flags=re.DOTALL
        )

    HTML_FILE.write_text(text, encoding="utf-8")
    print(f"Status: {old_status.upper()} → {status.upper()}")


def git_push():
    """Commit and push to GitHub."""
    # Set remote URL with token
    remote_url = f"https://{TOKEN}@github.com/Wahyuptr/tagihan-tetangga.git"
    git("remote", "set-url", "origin", remote_url)

    # Stage, commit, push
    rc, out, err = git("add", "tagihan.html")
    if rc != 0:
        print(f"git add error: {err}")
        return False

    rc, out, err = git("commit", "-m", f"Update status tagihan")
    if rc != 0 and "nothing to commit" not in err:
        print(f"git commit error: {err}")
        return False

    rc, out, err = git("push", "origin", "main")
    if rc != 0:
        print(f"git push error: {err}")
        return False

    print("✅ Git push berhasil — GitHub Pages update dalam 30 detik")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "show":
        show_status()
    elif cmd in ("lunas", "belum"):
        set_status(cmd)
        git_push()
    else:
        print(f"ERROR: perintah tidak dikenal: {cmd}")
        sys.exit(1)
