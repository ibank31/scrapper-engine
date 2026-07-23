def money(s):
    if not isinstance(s, str) or not s.strip(): return None
    t = s.replace("$", "").replace(",", "").strip()
    try: return float(t)
    except ValueError: return None
