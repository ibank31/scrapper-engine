# Scrapper Engine

Engine scraping pribadi (ibank31). Dua misi:
1. **Data affiliate** - foto/spek produk dari sumber resmi untuk situs affiliate (sortirin.com).
2. **Reward campaigns** - radar + detail campaign contentrewards.com untuk project clipping.

> Repo ini berisi data hasil scrape dan strategi pribadi. **Jaga tetap PRIVATE.**

## Struktur

```
core/                    helper bersama
  fetch.py               HTTP (UA, retry, timeout)
  nextjs_flight.py       decoder payload Next.js Flight
  pagemeta.py            og:image / twitter:image / deteksi gambar langsung
  imgconv.py             konversi webp (cwebp/dwebp atau ImageMagick)
  textutil.py            parsing uang dll
modules/
  reward_campaign/       scrape.py (radar) + pull_detail.py (detail per campaign)
  product_image/         foto hero produk dari halaman resmi (manifest-driven)
manifests/               input batch untuk product_image
data/                    output scrape (reward_campaign)
run.py                   dispatcher: python run.py <modul> [args]
```

## Setup (Termux)

```
pip install requests
pkg install -y libwebp          # untuk product_image
pip install deep-translator     # opsional, terjemahan brief campaign
```

## Pemakaian

```
python run.py reward_campaign
python run.py reward_detail <campaign_id>
python run.py product_image --manifest manifests/sortirin_photos.json --repo ~/sortirin
```

## Prinsip sumber (product_image)

Urutan kandidat di manifest = urutan prioritas:
1. Situs resmi brand (regional Indonesia > global).
2. Toko/distributor resmi (contoh: jblstore.co.id, anker.com.bd).
3. Marketplace = pilihan terakhir. Tandai jelas di `sumber`; risiko hak pakai lebih tinggi, wajib cek manual.

**Bot-wall (Akamai dll) tidak dilawan.** Kalau kena 403: ganti sumber di manifest, jangan tambah teknik bypass. Kasus nyata: www.jbl.com 403 -> id.jbl.com + jblstore.co.id sukses.
