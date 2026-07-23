"""Konversi gambar ke webp via cwebp/dwebp (libwebp) atau ImageMagick.
Termux: pkg install -y libwebp
"""
import os, random, string, subprocess, tempfile, time

MAX_KB = 250


class ConvertError(Exception):
    pass


def _has(binname):
    try:
        subprocess.run([binname, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def find_converter():
    if _has("magick"): return {"kind": "magick", "bin": "magick"}
    if _has("convert"): return {"kind": "magick", "bin": "convert"}
    if _has("cwebp"): return {"kind": "cwebp", "has_dwebp": _has("dwebp")}
    raise ConvertError("Tidak ada konverter gambar. Jalankan dulu: pkg install -y libwebp")


def is_webp(buf):
    return len(buf) > 12 and buf[0:4] == b"RIFF" and buf[8:12] == b"WEBP"


def _run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def to_webp(buf, conv=None, max_kb=MAX_KB):
    conv = conv or find_converter()
    tag = "%d-%s" % (int(time.time() * 1000), "".join(random.choices(string.ascii_lowercase + string.digits, k=6)))
    tmp = tempfile.gettempdir()
    tmp_in = os.path.join(tmp, "engine-in-" + tag)
    tmp_png = os.path.join(tmp, "engine-mid-" + tag + ".png")
    tmp_out = os.path.join(tmp, "engine-out-" + tag + ".webp")
    with open(tmp_in, "wb") as f:
        f.write(buf)
    try:
        if conv["kind"] == "magick":
            _run([conv["bin"], tmp_in, "-auto-orient", "-resize", "1200x1200>", "-quality", "82", tmp_out])
            out = open(tmp_out, "rb").read()
            if len(out) > max_kb * 1024:
                _run([conv["bin"], tmp_in, "-auto-orient", "-resize", "1000x1000>", "-quality", "70", tmp_out])
                out = open(tmp_out, "rb").read()
            return out
        src = tmp_in
        if is_webp(buf):
            if not conv.get("has_dwebp"):
                raise ConvertError("sumber webp tapi dwebp tidak ada")
            _run(["dwebp", tmp_in, "-o", tmp_png])
            src = tmp_png
        _run(["cwebp", "-quiet", "-q", "82", src, "-o", tmp_out])
        out = open(tmp_out, "rb").read()
        if len(out) > max_kb * 1024:
            _run(["cwebp", "-quiet", "-q", "82", "-resize", "1200", "0", src, "-o", tmp_out])
            out = open(tmp_out, "rb").read()
        if len(out) > max_kb * 1024:
            _run(["cwebp", "-quiet", "-q", "70", "-resize", "1000", "0", src, "-o", tmp_out])
            out = open(tmp_out, "rb").read()
        return out
    finally:
        for f in (tmp_in, tmp_png, tmp_out):
            try: os.remove(f)
            except OSError: pass
