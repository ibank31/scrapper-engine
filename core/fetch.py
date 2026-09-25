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

def _get_stream(url, headers, timeout):
    import requests
    return requests.get(url, headers=headers, timeout=timeout, stream=True)


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


def download_stream(url, destination, headers=None, retries=2, timeout=180, max_bytes=0, chunk_size=1024 * 1024):
    """Stream an HTTP response directly to a .part file without buffering it in RAM."""
    from pathlib import Path

    h = dict(DEFAULT_HEADERS)
    if headers:
        h.update(headers)
    target = Path(destination)
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(max(1, int(retries))):
        response = None
        try:
            response = _get_stream(url, h, timeout)
            if response.status_code != 200:
                last = "HTTP " + str(response.status_code)
                continue
            declared = int(response.headers.get("Content-Length") or 0)
            if max_bytes > 0 and declared > max_bytes:
                raise FetchError("response melebihi byte budget (%d B)" % max_bytes)
            part.unlink(missing_ok=True)
            total = 0
            with part.open("wb") as output:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if max_bytes > 0 and total > max_bytes:
                        raise FetchError("response melebihi byte budget (%d B)" % max_bytes)
                    output.write(chunk)
            if total <= 0:
                raise FetchError("empty response")
            part.replace(target)
            return total
        except FetchError:
            part.unlink(missing_ok=True)
            raise
        except Exception as exc:
            last = str(exc)
            part.unlink(missing_ok=True)
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
        if attempt < max(1, int(retries)) - 1:
            time.sleep(backoff_for_stream(attempt))
    raise FetchError(last or "unknown")


def backoff_for_stream(attempt):
    return 10 * (int(attempt) + 1)
