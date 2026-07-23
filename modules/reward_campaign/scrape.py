#!/usr/bin/env python3
# Reward Campaign Watcher - contentrewards.com/discover
# Output: data/reward_campaign/campaigns.json + DIGEST.md
# Mode: python scrape.py            -> fetch live
#       python scrape.py --blob F   -> parse blob hasil decode (flight.txt)
#       python scrape.py --local F  -> parse file html mentah
import json, re, sys, os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.fetch import fetch_text, FetchError
from core.nextjs_flight import decode_blob, parse_balanced, build_refmap
from core.textutil import money

URL = "https://contentrewards.com/discover"
OUT_DIR = os.path.join("data", "reward_campaign")
MY_PLATFORMS = {"tiktok", "youtube", "instagram"}
CAT_W = {"technology": 1.0, "education": 0.95, "news": 0.8, "product": 0.7,
         "personal brand": 0.6, "slideshow": 0.45, "other": 0.4, "none": 0.4,
         "entertainment": 0.3, "music": 0.15, "gaming": 0.15, "logo": 0.1}
KW_BONUS = ["ai ", " ai", "artificial intelligence", "startup", "founder", "business",
            "career", "podcast", "tech", "coding", "developer", "saas", "finance",
            "investing", "education", "science", "mit ", "book"]
BLOCK = ["casino", "gambl", "roobet", "betting", ".bet", " bet ", "penjamin", "cannabis",
         "vape", "nicotine", "onlyfans", "adult content", "18+"]

def fetch():
    try:
        return fetch_text(URL)
    except FetchError as e:
        raise SystemExit("fetch failed: " + str(e))

def collect(obj, out):
    if isinstance(obj, dict):
        if "totalBudget" in obj and "title" in obj: out.append(obj)
        for v in obj.values(): collect(v, out)
    elif isinstance(obj, list):
        for v in obj: collect(v, out)

def extract_campaigns(blob):
    raw = []; last_end = -1
    for m in re.finditer(r'\{"(?:id|avatar)":', blob):
        if m.start() < last_end: continue
        frag = parse_balanced(blob, m.start())
        if frag is None: continue
        try: obj = json.loads(frag)
        except Exception: continue
        tmp = []; collect(obj, tmp)
        if tmp:
            raw.extend(tmp); last_end = m.start() + len(frag)
    by_id = {}
    for c in raw:
        cid = c.get("id") or c.get("programId") or c.get("title")
        if cid not in by_id or len(c) > len(by_id[cid]): by_id[cid] = c
    return list(by_id.values())

def normalize(c, refmap, prev_ids):
    desc = c.get("description") or ""
    if isinstance(desc, str):
        m = re.fullmatch(r'\$([0-9a-f]{1,4})', desc)
        if m: desc = refmap.get(m.group(1), "")
    total = money(c.get("totalBudget")); spent = money(c.get("budgetSpent"))
    rate = money(c.get("pricePerView"))
    left = max(total - (spent or 0), 0) if total is not None else None
    plats = [p for p in (c.get("socialPlatforms") or []) if isinstance(p, str)]
    cat = str(c.get("category") or "none").lower()
    hay = " ".join([str(c.get("title", "")), str(c.get("brand", "")), str(c.get("whopProductRoute") or ""), desc]).lower()
    blocked = [b for b in BLOCK if b in hay]
    kw = [k for k in KW_BONUS if k in hay]
    rel = min(1.0, CAT_W.get(cat, 0.4) + min(len(kw) * 0.05, 0.25))
    rate_s = min(rate or 0, 15) / 15
    budget_s = min(left or 0, 50000) / 50000
    inter = MY_PLATFORMS & set(plats)
    plat_s = 1.0 if inter else (0.7 if not plats else 0.3)
    score = round(100 * (0.45 * rel + 0.25 * rate_s + 0.20 * budget_s + 0.10 * plat_s)
                  + (5 if c.get("isVerified") else 0), 1)
    flags = []
    if re.search(r'tier[ -]?1|usa only|us only|english[ -]speaking', hay): flags.append("EN/Tier-1")
    if blocked: flags.append("EXCLUDED:" + ",".join(sorted(set(blocked))[:2]))
    return {
        "id": c.get("id"), "title": c.get("title"), "brand": c.get("brand"),
        "category": cat, "type": c.get("campaignType"), "status": c.get("status"),
        "verified": bool(c.get("isVerified")), "rate_per_1k": rate,
        "budget_total": total, "budget_left": left,
        "progress_pct": round(c.get("progressPercentage") or 0, 1),
        "platforms": plats, "relevance": round(rel, 2), "score": score,
        "flags": flags, "excluded": bool(blocked),
        "link": ("https://contentrewards.com/discover/" + str(c.get("id"))) if c.get("id") else None,
        "new": c.get("id") not in prev_ids,
        "description": desc[:400],
    }

def fmt_money(v):
    return "-" if v is None else "$" + format(v, ",.0f")

def row(c):
    t = (c["title"] or "")[:42].replace("|", "/")
    nb = "NEW " if c["new"] else ""
    plat = ",".join(p[:2] for p in c["platforms"]) or "?"
    link = "[detail](" + c["link"] + ")" if c["link"] else "-"
    fl = " ".join(f for f in c["flags"] if not f.startswith("EXCLUDED"))
    rate = format(c["rate_per_1k"] or 0, "g")
    return ("| " + nb + t + " | " + (c["brand"] or "-") + " | " + str(c["score"]) + " | $"
            + rate + " | " + fmt_money(c["budget_left"]) + " | " + str(c["progress_pct"]) + "% | "
            + plat + " | " + c["category"] + " | " + (c["type"] or "-") + " | " + fl + " | " + link + " |")

HEAD = ("| Campaign | Brand | Skor | $/1K | Sisa budget | Terpakai | Platform | Kategori | Tipe | Flag | Link |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|")

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if "--blob" in sys.argv:
        blob = open(sys.argv[sys.argv.index("--blob") + 1], encoding="utf-8").read()
    elif "--local" in sys.argv:
        blob = decode_blob(open(sys.argv[sys.argv.index("--local") + 1], encoding="utf-8").read())
    else:
        blob = decode_blob(fetch())
    refmap = build_refmap(blob)
    prev_ids = set()
    prev_path = os.path.join(OUT_DIR, "campaigns.json")
    if os.path.exists(prev_path):
        try:
            prev_ids = set(c["id"] for c in json.load(open(prev_path))["campaigns"])
        except Exception: pass
    cams = [normalize(c, refmap, prev_ids) for c in extract_campaigns(blob)]
    active = [c for c in cams if c["status"] == "active" and c["progress_pct"] < 97]
    ok = [c for c in active if not c["excluded"]]
    ok = [c for c in ok if (MY_PLATFORMS & set(c["platforms"])) and str(c["type"] or "").lower() in ("clipping", "both")]
    relevant = sorted([c for c in ok if c["relevance"] >= 0.55], key=lambda x: -x["score"])
    offniche = sorted([c for c in ok if c["relevance"] < 0.55],
                      key=lambda x: -((x["rate_per_1k"] or 0) * min((x["budget_left"] or 0), 50000)))
    excluded = [c for c in active if c["excluded"]]
    wib = datetime.now(timezone(timedelta(hours=7)))
    n_new = sum(1 for c in active if c["new"])
    lines = [
        "# Reward Campaign Radar - " + wib.strftime("%d %b %Y %H:%M") + " WIB",
        "",
        "Sumber: " + URL + " | Total: **" + str(len(cams)) + "** | Aktif: **" + str(len(active))
        + "** | Baru sejak run terakhir: **" + str(n_new) + "**",
        "",
        "> WARM-UP RULE BinB: campaign clipping = arsip/referensi sampai accountPhase=mature. Jangan produksi campaign clip selama warm-up. Cek aturan tiap campaign (submission window, boosting, min views) sebelum eksekusi.",
        "",
        "## Relevan BinB - pantau/arsipkan (" + str(len(relevant)) + ")", "", HEAD,
    ]
    lines += [row(c) for c in relevant[:25]]
    lines += ["", "## Ekonomis tapi off-niche (top 15 dari " + str(len(offniche)) + ")", "", HEAD]
    lines += [row(c) for c in offniche[:15]]
    lines += ["", "## Dikecualikan otomatis: " + str(len(excluded)) + " (gambling/vape/dll)", ""]
    lines += ["- " + str(c["title"]) + " - " + ", ".join(c["flags"]) for c in excluded[:20]]
    open(os.path.join(OUT_DIR, "DIGEST.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump({"updated": wib.isoformat(), "count": len(cams), "campaigns": cams},
              open(prev_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("OK:", len(cams), "campaigns | aktif", len(active), "| relevan", len(relevant),
          "| excluded", len(excluded), "| baru", n_new)

if __name__ == "__main__":
    main()
