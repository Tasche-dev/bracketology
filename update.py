"""Pulls KenPom and EvanMiya and rewrites data.json. Run nightly by GitHub Actions.

KenPom needs a subscription: set KENPOM_EMAIL and KENPOM_PASSWORD as repository secrets.
If a source fails, its last known numbers are kept and marked "stale" so the page still builds.
"""
import difflib, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

SEASON = "2027"
DATA = Path(__file__).with_name("data.json")
old = json.loads(DATA.read_text()) if DATA.exists() else {"teams": []}
prev = {t["n"]: t for t in old["teams"]}
status = {}

ALIASES = {"ole miss": "mississippi", "miami fla": "miami fl", "miami ohio": "miami oh",
           "uconn": "connecticut", "usc": "southern california", "unc": "north carolina"}

def key(name):
    n = re.sub(r"[^a-z0-9 ]", "", name.lower().replace("&", " and ").replace("-", " "))
    n = re.sub(r"\bstate\b", "st", n)
    n = re.sub(r"\bsaint\b", "st", n)
    n = re.sub(r"\s+", " ", n).strip()
    return ALIASES.get(n, n)

def match(name, keys):
    k = key(name)
    if k in keys:
        return keys[k]
    close = difflib.get_close_matches(k, list(keys), n=1, cutoff=0.88)
    return keys[close[0]] if close else None

def col(df, *names):
    lowered = {c.lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lowered:
            return lowered[n.lower()]
    raise KeyError(f"none of {names} in {list(df.columns)}")

def rank(values, high_is_better=True):
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=high_is_better)
    r = [0] * len(values)
    for pos, i in enumerate(order, 1):
        r[i] = pos
    return r

def kenpom():
    email, pw = os.getenv("KENPOM_EMAIL"), os.getenv("KENPOM_PASSWORD")
    if not (email and pw):
        raise RuntimeError("KENPOM_EMAIL / KENPOM_PASSWORD not set")
    from kenpompy.utils import login
    import kenpompy.summary as ks
    df = ks.get_pomeroy_ratings(login(email, pw), season=SEASON)
    team, conf, wl = col(df, "Team"), col(df, "Conf"), col(df, "W-L")
    em, o, d, t = col(df, "AdjEM"), col(df, "AdjO"), col(df, "AdjD"), col(df, "AdjT")
    sos = col(df, "SOS-AdjEM", "SOS AdjEM", "SOS")
    f = lambda c: [float(str(x).replace("+", "")) for x in df[c]]
    ems, os_, ds, ts, ss = f(em), f(o), f(d), f(t), f(sos)
    kr, orr, drr, sr = rank(ems), rank(os_), rank(ds, False), rank(ss)
    out = []
    for i, row in enumerate(df.itertuples(index=False)):
        r = df.iloc[i]
        w, l = str(r[wl]).split("-")
        out.append({"n": re.sub(r"\s+\d+$", "", str(r[team])).strip(), "c": str(r[conf]), "w": int(w), "l": int(l),
                    "kp": kr[i], "net": ems[i], "sos": sr[i], "or": os_[i], "ork": orr[i],
                    "dr": ds[i], "drk": drr[i], "tp": ts[i]})
    if len(out) < 300:
        raise RuntimeError(f"only {len(out)} KenPom rows")
    return out

def evanmiya():
    from playwright.sync_api import sync_playwright
    rows, head = {}, []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("https://evanmiya.com/team-ratings", wait_until="networkidle", timeout=90000)
        pg.wait_for_selector("table tbody tr", timeout=60000)
        head = [re.sub(r"[^\w\- ]", "", h).strip() for h in
                pg.eval_on_selector_all("table thead th", "e=>e.map(x=>x.innerText)")]
        try:  # show as many rows per page as possible
            pg.locator("select:has(option[value='1000'])").first.select_option("1000")
            pg.wait_for_timeout(800)
        except Exception:
            pass
        for _ in range(15):
            for r in pg.eval_on_selector_all("table tbody tr",
                    "t=>t.map(r=>[...r.querySelectorAll('td')].map(td=>td.innerText.trim()))"):
                if r:
                    rows[r[0]] = r
            nxt = pg.get_by_text("Next", exact=True)
            if not nxt.count() or "disabled" in (nxt.first.get_attribute("class") or ""):
                break
            nxt.first.click()
            pg.wait_for_timeout(700)
        b.close()
    ix = lambda name: next(i for i, h in enumerate(head) if h.lower() == name.lower())
    ir, it, io, idf, ip = ix("Rank"), ix("Team"), ix("O-Rate"), ix("D-Rate"), ix("Preseason Team Rank")
    out = {}
    for r in rows.values():
        name = re.sub(r"[^\w\s.&'()-]", "", r[it]).strip()
        out[name] = {"em": int(r[ir]), "eo": float(r[io]), "ed": float(r[idf]), "pre": int(float(r[ip]))}
    if len(out) < 300:
        raise RuntimeError(f"only {len(out)} EvanMiya rows")
    return out

try:
    teams = kenpom()
    status["kenpom"] = "ok"
except Exception as e:
    print("KenPom failed:", e, file=sys.stderr)
    teams = [{k: v for k, v in t.items()} for t in old["teams"]]
    status["kenpom"] = "stale"

try:
    em = evanmiya()
    keys = {key(n): v for n, v in em.items()}
    miss = []
    for t in teams:
        m = match(t["n"], keys)
        if m:
            t.update(m)
        else:
            miss.append(t["n"])
            t.setdefault("em", 0), t.setdefault("pre", 0), t.setdefault("eo", 0), t.setdefault("ed", 0)
    print(f"EvanMiya matched {len(teams) - len(miss)}/{len(teams)}; unmatched sample: {miss[:15]}")
    status["evanmiya"] = "ok"
except Exception as e:
    print("EvanMiya failed:", e, file=sys.stderr)
    for t in teams:
        p = prev.get(t["n"], {})
        for k in ("em", "pre", "eo", "ed"):
            t.setdefault(k, p.get(k, 0))
    status["evanmiya"] = "stale"

if set(status.values()) == {"stale"} and old["teams"]:
    sys.exit("Both sources failed; leaving data.json unchanged.")
DATA.write_text(json.dumps({"updated": datetime.now(timezone.utc).isoformat(),
                            "sources": status, "teams": teams}, separators=(",", ":")))
print("Wrote", len(teams), "teams", status)
