#!/usr/bin/env python3
# Product Image Fetcher - foto hero produk dari halaman RESMI brand/distributor.
# Port Python dari fetch-photos.mjs (terbukti 14/14 di sortirin, Jul 2026).
#
# Usage (dari root scrapper-engine):
#   python run.py product_image --manifest manifests/sortirin_photos.json --repo ~/sortirin
#
# Alur per produk: halaman kandidat berurutan -> og:image/twitter:image ->
# unduh (min 5KB) -> webp (maks 1200px, <250KB) -> hero.webp + README sumber ->
# isi field "gambar" di content/products/{slug}.json -> salin ke folder review.
# Idempoten: SKIP kalau hero.webp sudah ada.
import argparse, json, os, shutil, sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.fetch import fetch_text, fetch_bytes, FetchError
from core.pagemeta import extract_og_image, is_direct_image
from core import imgconv

MOBILE_UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36"
H_HTML = {"User-Agent": MOBILE_UA, "Accept": "text/html,*/*"}
H_IMG = {"User-Agent": MOBILE_UA, "Accept": "image/*,*/*"}


def update_json(repo, slug, web_path):
    file = os.path.join(repo, "content", "products", slug + ".json")
    raw = open(file, encoding="utf-8").read()
    if '"gambar": []' not in raw:
        raise RuntimeError('field "gambar" tidak kosong / format beda di %s - tidak disentuh' % file)
    with open(file, "w", encoding="utf-8") as f:
        f.write(raw.replace('"gambar": []', '"gambar": [\n    "%s"\n  ]' % web_path))


def main():
    ap = argparse.ArgumentParser(description="Foto hero produk dari halaman resmi")
    ap.add_argument("--manifest", required=True, help="file JSON manifest produk")
    ap.add_argument("--repo", default=".", help="root repo situs (default: cwd)")
    ap.add_argument("--review-dir", default=None, help="folder salinan review (override manifest)")
    a = ap.parse_args()
    man = json.load(open(a.manifest, encoding="utf-8"))
    repo = os.path.expanduser(a.repo)
    review_dir = a.review_dir or man.get("review_dir")
    conv = imgconv.find_converter()
    ok, gagal, skip = [], [], []
    for it in man["products"]:
        slug, kategori = it["slug"], it["kategori"]
        pages, sumber = it["pages"], it.get("sumber", "?")
        print("\n=== %s ===" % slug)
        out_dir = os.path.join(repo, "public", "assets", "products", kategori, slug)
        out_file = os.path.join(out_dir, "hero.webp")
        if os.path.exists(out_file):
            print("SKIP: hero.webp sudah ada")
            skip.append(slug)
            continue
        done = False
        for page in pages:
            try:
                if is_direct_image(page):
                    img_url = page
                    buf = fetch_bytes(page, headers=H_IMG, retries=1, timeout=30, min_bytes=5000)
                else:
                    html = fetch_text(page, headers=H_HTML, retries=1, timeout=30)
                    img_url = extract_og_image(html)
                    if not img_url:
                        raise FetchError("og:image tidak ditemukan")
                    buf = fetch_bytes(img_url, headers=H_IMG, retries=1, timeout=30, min_bytes=5000)
                webp = imgconv.to_webp(buf, conv)
                os.makedirs(out_dir, exist_ok=True)
                with open(out_file, "wb") as f:
                    f.write(webp)
                with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
                    f.write("# Sumber foto\n\n- Jenis sumber: %s\n- Halaman: %s\n- URL gambar: %s\n- Diambil: %s\n- Diproses: resize maks 1200px, webp\n"
                            % (sumber, page, img_url, date.today().isoformat()))
                update_json(repo, slug, "/assets/products/%s/%s/hero.webp" % (kategori, slug))
                if review_dir:
                    try:
                        os.makedirs(review_dir, exist_ok=True)
                        shutil.copyfile(out_file, os.path.join(review_dir, slug + ".webp"))
                    except OSError:
                        pass
                print("OK  <- %s (%d KB)" % (img_url, round(len(webp) / 1024)))
                ok.append(slug); done = True
                break
            except Exception as e:
                print("  gagal via %s: %s" % (page, e))
        if not done:
            gagal.append(slug)
    print("\n===== RINGKASAN =====")
    print("OK    : %d" % len(ok))
    print("SKIP  : %d" % len(skip))
    print("GAGAL : %d%s" % (len(gagal), " -> " + ", ".join(gagal) if gagal else ""))
    if review_dir:
        print("\nFoto review: %s (cek satu per satu sebelum commit!)" % review_dir)
    sys.exit(1 if gagal else 0)

if __name__ == "__main__":
    main()
