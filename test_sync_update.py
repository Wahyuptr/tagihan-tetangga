#!/usr/bin/env python3
"""Tes sync_update.py (versi data JSON) — tanpa menyentuh repo asli & tanpa git push.

Menyalin sync_update.py + template.html ke tmpdir lalu menguji: periode 16-ke-16,
lunas melunasi tunggakan paling awal, belum hanya membatalkan periode berjalan,
migrasi dari tabel lama, badge untuk /api/status, dan tidak ada placeholder tersisa.
Jalankan: python3 test_sync_update.py
"""
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

SRC = Path(__file__).resolve().parent

LEGACY_HTML = """<html><body><div class="badge lunas"></div><table><tbody>
        <tr>
          <td>Oktober 2026</td>
          <td class="status-lunas">✅ LUNAS</td>
          <td>16 Oktober 2026</td>
        </tr>
        <tr>
          <td>September 2026</td>
          <td class="status-belum">❌ BELUM</td>
          <td>16 September 2026</td>
        </tr>
</tbody></table></body></html>"""


def load(tmp):
    spec = importlib.util.spec_from_file_location("su_test", tmp / "sync_update.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for f in ("sync_update.py", "template.html"):
            shutil.copy(SRC / f, self.tmp / f)
        self.s = load(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)


class Period(Base):
    def test_16_to_16(self):
        p = self.s.compute_period(datetime(2026, 10, 15, 23, 59))
        self.assertEqual((p["key"], p["due_date"]), ("2026-10", "15 Oktober 2026"))
        p = self.s.compute_period(datetime(2026, 10, 16, 0, 0))
        self.assertEqual((p["key"], p["period_range"]), ("2026-11", "16 Oktober – 16 November 2026"))
        p = self.s.compute_period(datetime(2026, 12, 20))
        self.assertEqual((p["key"], p["period_range"]), ("2027-01", "16 Desember 2026 – 16 Januari 2027"))
        p = self.s.compute_period(datetime(2027, 1, 5))
        self.assertEqual((p["key"], p["period_range"]), ("2027-01", "16 Desember 2026 – 16 Januari 2027"))

    def test_period_keys(self):
        self.assertEqual(self.s.period_keys("2026-08"), ["2026-06", "2026-07", "2026-08"])


class Marking(Base):
    def test_lunas_pays_oldest_arrears_first(self):
        d = self.s.load_data()
        d["paid"] = {"2026-06": "", "2026-07": "", "2026-08": "x", "2026-09": "x"}
        k = self.s.mark_lunas(d, datetime(2026, 10, 20))   # periode berjalan 2026-11, tunggakan 2026-10
        self.assertEqual(k, "2026-10")
        self.assertEqual(d["paid"]["2026-10"], "2026-10-20")
        self.assertNotIn("2026-11", d["paid"])
        self.assertEqual(self.s.mark_lunas(d, datetime(2026, 10, 20)), "2026-11")
        self.assertIsNone(self.s.mark_lunas(d, datetime(2026, 10, 20)))

    def test_belum_only_current_period(self):
        d = self.s.load_data()
        d["paid"] = {"2026-10": "2026-10-14"}
        self.assertIsNone(self.s.mark_belum(d, datetime(2026, 10, 17)))   # periode 2026-11
        self.assertEqual(d["paid"], {"2026-10": "2026-10-14"})
        self.assertEqual(self.s.mark_belum(d, datetime(2026, 10, 14)), "2026-10")
        self.assertEqual(d["paid"], {})


class Batal(Base):
    def test_batal_specific_period(self):
        d = self.s.load_data()
        d["paid"] = {"2026-10": "2026-10-14", "2026-11": "2026-10-20"}
        self.assertEqual(self.s.mark_batal(d, "2026-11"), "2026-11")
        self.assertEqual(d["paid"], {"2026-10": "2026-10-14"})
        self.assertIsNone(self.s.mark_batal(d, "2026-12"))
        with self.assertRaises(ValueError):
            self.s.mark_batal(d, "../x")


class Render(Base):
    def render(self, paid, when):
        d = self.s.load_data()
        d["paid"] = paid
        st = self.s.render(d, now=when)
        return st, (self.tmp / "tagihan.html").read_text(encoding="utf-8")

    def test_badge_and_data_roundtrip(self):
        st, html = self.render({"2026-10": "2026-10-14"}, datetime(2026, 10, 14, 9))
        self.assertEqual(st, "lunas")
        self.assertEqual(re.findall(r'class="badge (lunas|belum)"', html), ["lunas"])   # dipakai /api/status
        self.assertNotRegex(html, r"\{\{ [A-Z_]+ \}\}")
        self.assertEqual(self.s.load_data()["paid"], {"2026-10": "2026-10-14"})
        self.assertEqual(self.s.read_current_status(), "lunas" if datetime.now() < datetime(2026, 10, 16) else "belum")

    def test_new_period_is_belum(self):
        st, html = self.render({"2026-10": "2026-10-14"}, datetime(2026, 10, 16, 0, 5))
        self.assertEqual(st, "belum")
        self.assertIn('class="badge belum"', html)

    def test_no_private_network_details(self):
        _, html = self.render({}, datetime(2026, 10, 14))
        for secret in ("192.168.95.50", "6C:5A:B0", "ether5"):
            self.assertNotIn(secret, html)

    def test_json_cannot_break_script_tag(self):
        d = self.s.load_data()
        d["customer"] = "Pak </script><b>x"
        self.s.render(d, now=datetime(2026, 10, 14))
        html = (self.tmp / "tagihan.html").read_text(encoding="utf-8")
        blob = re.search(r'<script id="billing-data" type="application/json">(.*?)</script>', html, re.S).group(1)
        self.assertEqual(json.loads(blob)["customer"], "Pak </script><b>x")


class Migration(Base):
    def test_legacy_table_becomes_paid_map(self):
        (self.tmp / "tagihan.html").write_text(LEGACY_HTML, encoding="utf-8")
        d = self.s.load_data()
        self.assertEqual(d["paid"], {"2026-10": ""})
        self.assertEqual(d["amount"], 150000)


if __name__ == "__main__":
    unittest.main(verbosity=1)
