# 📡 Tagihan Internet Tetangga

Halaman tagihan otomatis untuk pelanggan PPPoE `radjamalik`.

**URL:** https://wahyuptr.github.io/tagihan-tetangga/

## Cara Kerja

```
User bayar → Telegram /lunas → MikroTik LUNAS_Tetangga
  → webhook ke billing-server → update tagihan.html
  → git push → GitHub Pages live dalam 30 detik
```

## File

| File | Fungsi |
|------|--------|
| `tagihan.html` | Halaman status tagihan (dark theme) |
| `sync_update.py` | Script update HTML + git push |

## Setup MikroTik

Script `Auto_Billing_Telegram` sudah memanggil webhook:
```
/tool fetch url="http://192.168.30.12:8080/api/blokir" mode=http http-method=post
```
