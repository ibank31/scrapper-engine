#!/usr/bin/env python3
# Campaign Detail Puller - tarik aturan + file campaign, translate ke Indonesia
# Usage:
#   python modules/reward_campaign/pull_detail.py <campaign_id_atau_url>
#   python modules/reward_campaign/pull_detail.py --local file.html
# Flags: --no-translate --no-download
import json, re, sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.fetch import fetch_text, FetchError, DEFAULT_HEADERS
from core.nextjs_flight import decode_blob, parse_balanced
from core.textutil import money

OUT_BASE = os.environ.get("CAMPAIGN_HOME", "/sdcard/BinB_Studio/Campaigns")

def fmt_money(s):
    v = money(s)
    return "-" if v is None else "$" + format(v, ",.2f").rstrip("0").rstrip(".")

def extract_detail(blob):
    for marker in ('"payouts":', '"contentRequirements":', '"referenceMaterials":'):
        k = blob.find(marker)
        if k < 0: continue
        start = blob.rfind('{', 0, k)
        while start >= 0:
            frag = parse_balanced(blob, start)
            try: obj = json.loads(frag) if frag else None
            except Exception: obj = None
            if isinstance(obj, dict) and obj.get("id") and ("payouts" in obj or "contentRequirements" in obj):
                req_items = (obj.get("contentRequirements") or {}).get("items") or []
                requirements = [{"text": str(item), "isMandatory": True} for item in req_items]
                resources = [{"label": r.get("type") or "reference material", "platform": "all", "url": r.get("url")} for r in (obj.get("referenceMaterials") or []) if r.get("url")]
                campaign = dict(obj)
                campaign.update({"brand": obj.get("organizationName") or obj.get("brand"), "socialPlatforms": obj.get("platforms") or [], "campaignType": obj.get("payoutType") or obj.get("type"), "status": obj.get("status") or "active"})
                return {"campaign": campaign, "staticDetails": {"requirements": requirements, "resources": resources, "payouts": obj.get("payouts") or []}}
            start = blob.rfind('{', 0, start)
    raise SystemExit("detail campaign tidak ditemukan - struktur halaman berubah?")

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
                resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=120, stream=True)
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
        try:
            html = fetch_text(url, retries=1)
        except FetchError as e:
            raise SystemExit(str(e) + " - cek id campaign")
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
