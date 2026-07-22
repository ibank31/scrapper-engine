#!/usr/bin/env python3
# Campaign Detail Puller - tarik aturan + file campaign, translate ke Indonesia
# Usage:
#   python modules/reward_campaign/pull_detail.py <campaign_id_atau_url>
#   python modules/reward_campaign/pull_detail.py --local file.html
# Flags: --no-translate --no-download
import json, re, sys, os, time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
OUT_BASE = os.environ.get("CAMPAIGN_HOME", "/sdcard/BinB_Studio/Campaigns")

def money(s):
    if not isinstance(s, str) or not s.strip(): return None
    t = s.replace("$", "").replace(",", "").strip()
    try: return float(t)
    except ValueError: return None

def fmt_money(s):
    v = money(s)
    return "-" if v is None else "$" + format(v, ",.2f").rstrip("0").rstrip(".")

def decode_blob(html):
    parts = []
    for m in CHUNK_RE.finditer(html):
        c = m.group(1)
        try: parts.append(json.loads('"' + c + '"'))
        except Exception: parts.append(c.encode().decode("unicode_escape", "ignore"))
    return "\n".join(parts)

def parse_balanced(s, start):
    depth = 0; i = start; instr = False; esc = False
    while i < len(s):
        c = s[i]
        if instr:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': instr = False
        else:
            if c == '"': instr = True
            elif c in "{[": depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0: return s[start:i + 1]
        i += 1
    return None

def extract_detail(blob):
    k = blob.find('"staticDetails"')
    if k < 0: raise SystemExit("staticDetails tidak ditemukan - struktur halaman berubah?")
    start = blob.rfind('{"campaign":', 0, k)
    if start < 0: raise SystemExit("objek campaign tidak ditemukan")
    frag = parse_balanced(blob, start)
    return json.loads(frag)

def make_translator(enabled):
    if not enabled:
        return lambda t: None
    try:
        from deep_translator import GoogleTranslator
        g = GoogleTranslator(source="auto", target="id")
        def tr(t):
            try: return g.translate(t[:4500])
            except Exception: return None
        return tr
    except Exception:
        print("(!) deep-translator tidak terpasang. Jalankan: pip install deep-translator")
        return lambda t: None

def download_resources(resources, dest):
    os.makedirs(dest, exist_ok=True)
    for r in resources:
        url = r.get("url") or ""
        label = r.get("label") or "file"
        print("-> download:", label, "|", url)
        try:
            if "drive.google.com" in url:
                import gdown
                if "/folders/" in url:
                    gdown.download_folder(url=url, output=os.path.join(dest, label), quiet=False, use_cookies=False)
                else:
                    gdown.download(url=url, output=os.path.join(dest, label), quiet=False, fuzzy=True)
            else:
                import requests
                resp = requests.get(url, headers=HEADERS, timeout=120, stream=True)
                resp.raise_for_status()
                name = re.sub(r'[^A-Za-z0-9._-]', '_', url.split("?")[0].split("/")[-1] or label)
                with open(os.path.join(dest, name), "wb") as f:
                    for chunk in resp.iter_content(65536): f.write(chunk)
            print("   OK")
        except Exception as e:
            print("   GAGAL:", str(e)[:120])
            print("   Download manual di browser:", url)

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_tr = "--no-translate" in sys.argv
    no_dl = "--no-download" in sys.argv
    local = "--local" in sys.argv
    if not args: raise SystemExit("kasih campaign id / URL / file html")
    if local:
        html = open(args[0], encoding="utf-8").read()
    else:
        m = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', args[0])
        cid = m.group(0) if m else args[0]
        url = "https://contentrewards.com/discover/" + cid
        import requests
        r = requests.get(url, headers=HEADERS, timeout=60)
        if r.status_code != 200: raise SystemExit("HTTP " + str(r.status_code) + " - cek id campaign")
        html = r.text
    d = extract_detail(decode_blob(html))
    c = d["campaign"]; sd = d.get("staticDetails") or {}
    tr = make_translator(not no_tr)
    slug = re.sub(r'[^A-Za-z0-9]+', '-', (c.get("title") or "campaign")).strip("-").lower()[:50]
    out_dir = os.path.join(OUT_BASE, slug)
    os.makedirs(out_dir, exist_ok=True)
    total = fmt_money(c.get("totalBudget")); spent = fmt_money(c.get("budgetSpent"))
    lines = [
        "# " + (c.get("title") or "?"),
        "",
        "- Brand: " + str(c.get("brand")),
        "- Kategori: " + str(c.get("category")) + " | Tipe: " + str(c.get("campaignType")) + " | Status: " + str(c.get("status")),
        "- Budget: " + total + " (terpakai " + spent + ")",
        "- Platform: " + ", ".join(c.get("socialPlatforms") or []),
        "- Link campaign: https://contentrewards.com/discover/" + str(c.get("id")),
        "- Join (manual): https://whop.com/" + str(c.get("whopProductRoute") or "?"),
        "",
        "> PENGINGAT BinB: warm-up = konten original saja; campaign clipping diarsip dulu. Upload selalu manual.",
        "",
        "## Deskripsi", "",
        (c.get("description") or "-").strip(),
    ]
    t = tr(c.get("description") or "")
    if t: lines += ["", "**ID:** " + t]
    pay = sd.get("payouts") or []
    if pay:
        lines += ["", "## Bayaran per platform", "", "| Platform | CPM/1K | Min views | Max payout |", "|---|---|---|---|"]
        for p in pay:
            lines.append("| " + str(p.get("platform")) + " | " + fmt_money(p.get("cpm")) + " | " + str(p.get("minViews") or "-") + " | " + fmt_money(p.get("maxPayout")) + " |")
    reqs = sd.get("requirements") or []
    if reqs:
        lines += ["", "## Aturan (" + str(len(reqs)) + ")", ""]
        for i, rq in enumerate(reqs, 1):
            tag = "[WAJIB] " if rq.get("isMandatory") else "[opsional] "
            plat = "" if rq.get("platform") in (None, "all") else "(" + str(rq.get("platform")) + ") "
            txt = (rq.get("text") or "").strip()
            lines.append(str(i) + ". " + tag + plat + txt)
            ti = tr(txt)
            if ti: lines.append("   - ID: " + ti)
    res = sd.get("resources") or []
    if res:
        lines += ["", "## File / resource", ""]
        for r in res:
            lines.append("- " + str(r.get("label")) + " (" + str(r.get("platform")) + "): " + str(r.get("url")))
    brief = os.path.join(out_dir, "BRIEF.md")
    open(brief, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump(d, open(os.path.join(out_dir, "detail.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("OK:", brief, "| aturan:", len(reqs), "| payout:", len(pay), "| resource:", len(res))
    if res and not no_dl:
        download_resources(res, os.path.join(out_dir, "files"))
    elif res:
        print("(--no-download) link file ada di BRIEF.md")

if __name__ == "__main__":
    main()
