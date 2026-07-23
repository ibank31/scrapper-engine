"""HTTP fetch bersama: UA konsisten, retry, timeout.
Catatan strategi: engine ini TIDAK melawan bot-wall (Akamai dll).
Kalau kena 403, solusinya pindah sumber (lihat README), bukan tambah teknik.
"""
import time

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class FetchError(Exception):
    pass


def _get(url, headers, timeout):
    import requests
    return requests.get(url, headers=headers, timeout=timeout)


def fetch_text(url, headers=None, retries=3, timeout=60, backoff=15):
    h = dict(DEFAULT_HEADERS)
    if headers: h.update(headers)
    last = None
    for attempt in range(retries):
        try:
            r = _get(url, h, timeout)
            if r.status_code == 200:
                return r.text
            last = "HTTP " + str(r.status_code)
        except Exception as e:
            last = str(e)
        if attempt < retries - 1:
            time.sleep(backoff * (attempt + 1))
    raise FetchError(last or "unknown")


def fetch_bytes(url, headers=None, retries=1, timeout=60, backoff=10, min_bytes=0):
    h = dict(DEFAULT_HEADERS)
    if headers: h.update(headers)
    last = None
    for attempt in range(retries):
        try:
            r = _get(url, h, timeout)
            if r.status_code == 200:
                if min_bytes and len(r.content) < min_bytes:
                    raise FetchError("gambar terlalu kecil (%d B)" % len(r.content))
                return r.content
            last = "HTTP " + str(r.status_code)
        except FetchError:
            raise
        except Exception as e:
            last = str(e)
        if attempt < retries - 1:
            time.sleep(backoff * (attempt + 1))
    raise FetchError(last or "unknown")
