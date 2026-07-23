"""Ekstraksi metadata halaman: og:image / twitter:image, deteksi URL gambar langsung."""
import re

_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']', re.I),
]

_IMG_EXT = re.compile(r'\.(jpe?g|png|webp|avif)(\?|$)', re.I)


def extract_og_image(html):
    for p in _PATTERNS:
        m = p.search(html)
        if m:
            u = m.group(1).replace("&amp;", "&").strip()
            if u.startswith("//"): u = "https:" + u
            return u
    return None


def is_direct_image(url):
    return bool(_IMG_EXT.search(url)) or "/cdn/shop/" in url
