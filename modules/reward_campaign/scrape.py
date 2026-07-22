import json, re, sys, datetime, pathlib
import requests

URL = "https://whop.com/discover/content-rewards/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
OUT = pathlib.Path("data/reward_campaign")
MY_PLATFORMS = {"tiktok", "youtube", "instagram"}  # sesuaikan akunmu

def fetch_html():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def extract_campaigns(html):
    """Ambil objek JSON campaign yang tertanam di script Next.js."""
    campaigns = []
    # kumpulkan semua blob JSON di dalam <script>
    for chunk in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S):
        text = chunk.encode().decode("unicode_escape", errors="ignore")
        # cari objek yang punya ciri khas campaign
        for m in re.finditer(r'\{[^{}]*"rewardRate"[^{}]*\}', text):
            try:
                campaigns.append(json.loads(m.group()))
            except json.JSONDecodeError:
                pass
    return campaigns

def score(c):
    rate = float(c.get("rewardRate") or 0)          # $ per 1k views
    total = float(c.get("totalBudget") or 0)
    spent = float(c.get("spentBudget") or 0)
    left = max(total - spent, 0)
    platforms = {p.lower() for p in c.get("platforms", [])}
    platform_ok = 1 if platforms & MY_PLATFORMS else 0
    return rate * (left / total if total else 0) * platform_ok, left

def main():
    html = fetch_html()
    if "--dump" in sys.argv:  # mode debug: simpan HTML mentah utk tuning
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "raw.html").write_text(html)
        return
    rows = []
    for c in extract_campaigns(html):
        s, left = score(c)
        rows.append({**c, "budgetLeft": left, "worthScore": round(s, 2)})
    rows.sort(key=lambda r: r["worthScore"], reverse=True)

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.utcnow().isoformat()
    (OUT / "campaigns.json").write_text(json.dumps(
        {"updatedAt": stamp, "campaigns": rows}, indent=2))

    digest = ["# Whop Campaign Digest", f"_Updated: {stamp} UTC_", ""]
    for r in rows[:15]:
        digest.append(
            f"- **{r.get('title','?')}** — ${r.get('rewardRate','?')}/1k views, "
            f"sisa budget ${r['budgetLeft']:.0f}, skor {r['worthScore']}")
    (OUT / "DIGEST.md").write_text("\n".join(digest))

if __name__ == "__main__":
    main()
