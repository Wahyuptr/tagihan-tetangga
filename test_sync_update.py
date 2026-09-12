#!/usr/bin/env python3
"""Test harness sync_update.py — verifikasi bugfix baris riwayat periode berjalan.

Menyalin sync_update.py + template.html ke tmpdir, lalu render lunas/belum
dan memeriksa HTML hasil. Tidak menyentuh repo asli & tidak git push.
"""
import importlib.util
import re
import shutil
import sys
import tempfile
from pathlib import Path

SRC = Path("/home/hermes/backup-mikrotik/tagihan-tetangga")
FAKE_OLD_HTML = """<html><body>
<div class="badge belum"><span class="dot"></span> BELUM LUNAS</div>
<table><tbody>
        <tr>
          <td>Agustus 2026</td>
          <td class="status-belum">\u274c BELUM</td>
          <td>16 Agustus 2026</td>
        </tr>
        <tr>
          <td>Juli 2026</td>
          <td class="status-lunas">\u2705 LUNAS</td>
          <td>16 Juli 2026</td>
        </tr>
</tbody></table></body></html>
"""

failures = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        failures.append(label)


def run(status):
    tmp = Path(tempfile.mkdtemp(prefix="synctest-"))
    shutil.copy(SRC / "sync_update.py", tmp / "sync_update.py")
    shutil.copy(SRC / "template.html", tmp / "template.html")
    (tmp / "tagihan.html").write_text(FAKE_OLD_HTML, encoding="utf-8")

    spec = importlib.util.spec_from_file_location("sync_under_test", tmp / "sync_update.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.render(status)
    html = (tmp / "tagihan.html").read_text(encoding="utf-8")
    shutil.rmtree(tmp)
    return html


def current_row(html):
    """Row riwayat untuk periode berjalan (baris pertama tabel)."""
    m = re.search(r"<tr>\s*<td>(\w+ \d{4})</td>\s*<td class=\"(status-\w+)\">([^<]+)</td>", html)
    return m.groups() if m else (None, None, None)


def badge(html):
    m = re.search(r'class="badge (lunas|belum)"', html)
    return m.group(1) if m else None


print("T1: render lunas")
h = run("lunas")
check("badge = lunas", badge(h) == "lunas", badge(h))
bln, cls, txt = current_row(h)
check("baris periode berjalan = status-lunas", cls == "status-lunas", f"{bln}/{cls}")
check("teks baris = LUNAS", "LUNAS" in (txt or ""), txt)
check("placeholder {{ }} habis ter-render", "{{" not in h)

print("T2: render belum")
h2 = run("belum")
check("badge = belum", badge(h2) == "belum", badge(h2))
bln2, cls2, txt2 = current_row(h2)
check("baris periode berjalan = status-belum", cls2 == "status-belum", f"{bln2}/{cls2}")

print("T3: history bulan lampau dipertahankan")
check("baris Agustus 2026 masih ada (BELUM)", "Agustus 2026" in h and "status-belum" in h)
check("baris Juli 2026 tetap LUNAS",
      re.search(r"Juli 2026</td>\s*<td class=\"status-lunas\">", h) is not None)
check("jumlah baris riwayat = 4 (Sep, Agu, Jul, Jun)",
      len(re.findall(r"<td>\w+ \d{4}</td>", h)) == 4,
      str(len(re.findall(r"<td>\w+ \d{4}</td>", h))))

print()
if failures:
    print(f"HASIL: {len(failures)} FAIL -> {failures}")
    sys.exit(1)
print("HASIL: SEMUA TEST LULUS")
