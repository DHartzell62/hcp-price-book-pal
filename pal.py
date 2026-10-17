"""HCP Price Book Pal: download your Housecall Pro price book to a spreadsheet.

Free tool from Hartzell's Heat & Air, Kingfisher OK. Runs on YOUR computer with YOUR HCP login.
Your password is typed into HCP's own login page and never leaves this machine.

  python pal.py login      opens a browser, you log into HCP once (saved outside this folder, under AppData, Local, HCPPriceBookPal)
  python pal.py pull       downloads services + materials to pricebook.csv (+ a snapshot for push)

Then edit pricebook.csv (by hand, or with ChatGPT / Claude, see README.md) and run pal_push.py.
This uses the same private connection HCP's website uses. It is not an official HCP product.
"""
import csv, json, os, re, shutil, stat, sys, time
from datetime import datetime
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
# The HCP login lives OUTSIDE the tool folder, so zipping or sharing the folder never hands over a login.
PROFILE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "HCPPriceBookPal", "hcp_profile")
UUID_OK = re.compile(r"^[a-z]+_[0-9a-f]{32}$")


def safe_uuid(u):
    """Every HCP id goes into a web address and a file name, so it must look exactly like an HCP id."""
    if not isinstance(u, str) or not UUID_OK.match(u):
        sys.exit(f"Refusing an item id that does not look like an HCP id: {u!r}")
    return u


def new_run_dir(suffix=""):
    """A fresh backups/<date-time><suffix> folder that never collides with an earlier one."""
    base = os.path.join(HERE, "backups", datetime.now().strftime("%Y%m%d_%H%M%S"))
    for i in range(1000):
        path = base + (f"_{i}" if i else "") + suffix
        try:
            os.makedirs(path); return path
        except FileExistsError:
            continue
    sys.exit("Could not make a backup folder. Nothing was written.")


def shown(text):
    """Strip control characters before printing, so no item name can hide lines of a preview."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(text))
CSV_OUT = os.path.join(HERE, "pricebook.csv")
SNAP = os.path.join(HERE, "pricebook_snapshot.json")
ORIGINALS = os.path.join(HERE, "original_backups")  # one dated folder per download, never overwritten
BASE = "https://pro.housecallpro.com/alpha/pricebook"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
PAGE = 200
COLS = ["type", "uuid", "category", "name", "description", "price", "cost"]


FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "'")  # a leading apostrophe too, so a real one survives


def _defang(v):
    """Excel runs a cell starting with = + - @ as a formula (CSV injection). A leading apostrophe makes it text."""
    return "'" + v if isinstance(v, str) and v.startswith(FORMULA_START) else v


def _refang(v):
    return v[1:] if isinstance(v, str) and v.startswith("'") and v[1:2] and v[1:].startswith(FORMULA_START) else v


def write_csv(path, rows, cols, mode="w"):
    """Every spreadsheet this tool writes goes through here."""
    with open(path, mode, newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        w.writerows({k: _defang(r.get(k, "")) for k in cols} for r in rows)


def read_csv(path):
    """Every spreadsheet this tool reads comes through here."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k: _refang(v) for k, v in r.items()} for r in csv.DictReader(f)]


def keep_copy(path):
    """Before pricebook.csv is overwritten, save the current one, so no edits are ever lost."""
    if os.path.exists(path):
        d = os.path.join(HERE, "spreadsheet_history"); os.makedirs(d, exist_ok=True)
        shutil.copy2(path, os.path.join(d, datetime.now().strftime("pricebook_%Y-%m-%d_%H%M%S.csv")))


def login():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(PROFILE, headless=False, user_agent=UA,
                                                    viewport={"width": 1280, "height": 850})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://pro.housecallpro.com/app/dashboard")
        print("Log into Housecall Pro in the browser window. This closes by itself when you are in.")
        for _ in range(600):
            page.wait_for_timeout(1000)
            if "/app/" in page.url and "log_in" not in page.url:
                break
        else:
            ctx.close(); sys.exit("Timed out waiting for login.")
        page.wait_for_timeout(3000)
        ctx.close()
    print("Logged in. Saved in", PROFILE)


def logout():
    if os.path.isdir(PROFILE):
        shutil.rmtree(PROFILE, ignore_errors=True)
    print("Logged out: the saved HCP login was deleted from this computer." if not os.path.isdir(PROFILE)
          else f"Could not delete {PROFILE}. Close any open browser windows and try again.")


def session():
    """Two cookies from the saved profile: the HCP session and its CSRF token."""
    from playwright.sync_api import sync_playwright
    if not os.path.isdir(PROFILE):
        sys.exit("Run 'python pal.py login' first.")
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(PROFILE, headless=True, user_agent=UA)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://pro.housecallpro.com/app/dashboard", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        if "log_in" in page.url:
            ctx.close(); sys.exit("Your HCP login expired. Run 'python pal.py login' again.")
        ck = {c["name"]: c["value"] for c in ctx.cookies() if "housecallpro.com" in c.get("domain", "")}
        ctx.close()
    sess, csrf = ck.get("_housecall-web_session_with_domain"), ck.get("csrf_token")
    if not sess or not csrf:
        sys.exit("Could not read the HCP login. Run 'python pal.py login' again.")
    s = requests.Session()
    s.cookies.set("_housecall-web_session_with_domain", sess, domain="pro.housecallpro.com")
    s.cookies.set("csrf_token", csrf, domain="pro.housecallpro.com")
    s.headers.update({"User-Agent": UA, "x-csrf-token": csrf, "Accept": "application/json",
                      "Content-Type": "application/json",
                      "Referer": "https://pro.housecallpro.com/app/settings/price_book/services"})
    s.max_redirects = 0  # never follow a redirect: the login token must only ever go to HCP
    return s


def get(s, url, params=None):
    for i in range(3):
        r = s.get(url, params=params, timeout=30)
        if r.status_code in (401, 403):
            sys.exit("HCP refused the login (%s). Run 'python pal.py login' again." % r.status_code)
        if r.status_code == 200:
            return r.json()
        time.sleep(8)  # HCP throttles; back off and retry
    r.raise_for_status()


def paged(s, url, params):
    out, p, seen = [], 1, set()
    while p <= 500:
        d = get(s, url, {**params, "page": p, "page_size": PAGE})
        chunk = d.get("data", [])
        ids = {c.get("uuid") for c in chunk}
        if ids and ids <= seen:
            return out  # HCP sent the same page again: stop instead of looping forever
        seen |= ids
        out.extend(chunk)
        if not chunk or (p >= d.get("total_pages_count", 1) and len(chunk) < PAGE):
            return out  # a full page always means ask for the next one, whatever the page count says
        p += 1
    sys.exit("Stopped: HCP kept sending pages past 500. Nothing was written. Try again later.")


def walk(s, cat_url, item_url, item_key, roots, kind):
    rows, raw, seen, stack = [], [], set(), [([c["name"]], c) for c in roots]
    while stack:
        path, cat = stack.pop()
        if cat["uuid"] in seen:
            continue
        seen.add(cat["uuid"])
        for ch in paged(s, cat_url, {"parent_uuid": cat["uuid"]}):
            stack.append((path + [ch["name"]], ch))
        items = paged(s, item_url, {item_key: cat["uuid"]})
        for it in items:
            raw.append({"type": kind, "category": " / ".join(path), "item": it})
            rows.append({"type": kind, "uuid": it["uuid"], "category": " / ".join(path),
                         "name": it.get("name") or "", "description": (it.get("description") or "").replace("\r", ""),
                         "price": f"{(it.get('price') or 0) / 100:.2f}", "cost": f"{(it.get('cost') or 0) / 100:.2f}"})
        if items:
            print(f"  {len(items):4d} {kind}s  {' / '.join(path)}")
        time.sleep(0.4)
    return rows, raw


def pull():
    s = session()
    rows, raw = [], []
    for ind in get(s, f"{BASE}/industries").get("data", []):
        roots = paged(s, f"{BASE}/categories", {"pricebook_industry_uuid": ind["uuid"], "id": "_root"})
        r, w = walk(s, f"{BASE}/categories", f"{BASE}/services", "pricebook_category_uuid", roots, "service")
        rows += r; raw += w
    roots = paged(s, f"{BASE}/material_categories", {"id": "_root"})
    r, w = walk(s, f"{BASE}/material_categories", f"{BASE}/materials", "material_category_uuid", roots, "material")
    rows += r; raw += w
    # Permanent copy of exactly what HCP had, before anyone edits anything. Read-only, never overwritten.
    keep = os.path.join(ORIGINALS, datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    os.makedirs(keep)
    full = os.path.join(keep, "full_pricebook_from_hcp.json")
    json.dump({"pulled_at": datetime.now().isoformat(timespec="seconds"), "items": raw},
              open(full, "x", encoding="utf-8"), ensure_ascii=True, indent=1)
    copy = os.path.join(keep, "pricebook_original.csv")
    write_csv(copy, rows, COLS, mode="x")
    for fn in (full, copy):
        os.chmod(fn, stat.S_IREAD)
    keep_copy(CSV_OUT)
    write_csv(CSV_OUT, rows, COLS)
    json.dump({"pulled_at": datetime.now().isoformat(timespec="seconds"),
               "rows": {r["uuid"]: r for r in rows}}, open(SNAP, "w", encoding="utf-8"), ensure_ascii=True, indent=0)
    n = sum(r["type"] == "service" for r in rows)
    print(f"\nDone: {n} services, {len(rows) - n} materials -> {CSV_OUT}")
    print(f"Your untouched original is saved in {keep}")
    print("Keep that folder. It is how you put everything back (menu: Put EVERYTHING back the way it was).")
    print("Edit pricebook.csv, keep the uuid and type columns as they are, then preview with: python pal_push.py --preview")


def friendly(fn):
    """Run a step; if HCP bounces us to its login page (a redirect), say so in plain words."""
    try:
        fn()
    except requests.TooManyRedirects:
        sys.exit("HCP sent this tool to its login page, so your login has expired. Use 'Log into Housecall Pro' "
                 "again. Anything already done is in the backups folder.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    friendly({"login": login, "logout": logout, "pull": pull}.get(cmd, lambda: print(__doc__)))
