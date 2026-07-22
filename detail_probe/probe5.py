import requests, re, os

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
# Campaign uji: Dreamina AI
CID = "fc7ba8d6-8d5c-4d1b-ac4d-dca047eeecd1"
PID = "09a289b7-900f-4daf-bd46-a636dd6a731f"
EXP = "exp_SgwOjv4LH9NGEI"
ROUTE = "propaganda-clippers"

urls = [
    "https://contentrewards.com/campaign/" + CID,
    "https://contentrewards.com/campaigns/" + CID,
    "https://contentrewards.com/c/" + CID,
    "https://contentrewards.com/discover/" + CID,
    "https://contentrewards.com/program/" + PID,
    "https://contentrewards.com/api/campaigns/" + CID,
    "https://whop.com/" + ROUTE + "/",
    "https://whop.com/experiences/" + EXP,
]
KEYS = ["requirement", "rules", "Rules", "drive.google", "dropbox", "getContent",
        "assets", "submission", "minimum", "__next_f", "description"]

os.makedirs("detail_probe", exist_ok=True)
for i, u in enumerate(urls):
    try:
        r = requests.get(u, headers=H, timeout=40, allow_redirects=True)
        body = r.text
        counts = " ".join(k + ":" + str(body.count(k)) for k in KEYS)
        print(i, "|", r.status_code, "|", len(body), "|", u)
        print("   ", counts)
        if r.status_code == 200 and len(body) > 20000:
            open("detail_probe/p" + str(i) + ".html", "w", encoding="utf-8").write(body)
            print("    saved -> detail_probe/p" + str(i) + ".html")
    except Exception as e:
        print(i, "| ERR |", u, "|", str(e)[:80])
