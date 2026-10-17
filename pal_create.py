"""HCP Price Book Pal: add the missing services you priced.

  python pal_create.py --preview            shows what would be added, writes nothing
  python pal_create.py --apply              adds exactly what the last preview showed
  python pal_create.py --remove <folder>    preview removing the services one add run created
  python pal_create.py --remove <folder> --apply

Fill in your_price (and your_cost if you track it) in missing_services.csv. Only rows with a price are added.
Every new service goes into one category, "Added by Price Book Pal", with ONLINE BOOKING OFF (HCP turns it
on by default for new services; this tool turns it off and checks). Turn booking on yourself in HCP when the
price is final. Each run is logged so it can be removed again.
"""
import hashlib, json, os, sys, time
from datetime import datetime
from pal import BASE, HERE, session, paged, read_csv, safe_uuid, shown, new_run_dir
from pal_push import cents, call, save_log
from pal_library import MISSING

CAT_NAME = "Added by Price Book Pal"
API = BASE + "/"
PREVIEW_STAMP = os.path.join(HERE, ".add_preview.json")


def unwrap(j):
    for k in ("service", "category"):
        if isinstance(j, dict) and k in j:
            return j[k]
    return j


def wanted():
    if not os.path.exists(MISSING):
        sys.exit("Run the missing-services step first (python pal_library.py missing).")
    out, refused, seen = [], [], set()
    for r in read_csv(MISSING):
        if not (r.get("your_price") or "").strip():
            continue
        p, c = cents(r["your_price"]), cents(r.get("your_cost") or "0")
        name = (r.get("name") or "").strip()
        if p is None or c is None or p < 0 or c < 0:
            refused.append((name, "price or cost is not a plain dollar amount of zero or more")); continue
        if not name or name.lower() in seen:
            refused.append((name, "blank or duplicate name")); continue
        seen.add(name.lower())
        out.append({"name": name, "description": r.get("description") or "", "price": p, "cost": c,
                    "taxable": (r.get("taxable") or "").strip().upper().startswith("Y")})
    return out, refused


def plan_hash(todo):
    return hashlib.sha256(json.dumps(todo, sort_keys=True).encode()).hexdigest()


def existing_names(s):
    names = set()
    for ind in s.get(API + "industries", timeout=30).json().get("data", []):
        stack = paged(s, API + "categories", {"pricebook_industry_uuid": ind["uuid"], "id": "_root"})
        while stack:
            c = stack.pop()
            stack += paged(s, API + "categories", {"parent_uuid": c["uuid"]})
            names |= {x["name"].strip().lower() for x in paged(s, API + "services", {"pricebook_category_uuid": c["uuid"]})}
    return names


def category(s, dry):
    ind = s.get(API + "industries", timeout=30).json()["data"][0]["uuid"]
    for c in paged(s, API + "categories", {"pricebook_industry_uuid": ind, "id": "_root"}):
        if c["name"] == CAT_NAME:
            return c["uuid"]
    if dry:
        return None
    r = s.post(API + "categories", json={"name": CAT_NAME, "pricebook_industry_uuid": ind}, timeout=30)  # no retry
    r.raise_for_status()
    return safe_uuid(unwrap(r.json())["uuid"])


def gone(s, u):
    return call(s, "get", API + "services/" + u).status_code == 404


def clean_up(s, cat, name, log, run):
    """A create went wrong. Find anything HCP made under that name in our category and remove it, proving it."""
    left = []
    for x in paged(s, API + "services", {"pricebook_category_uuid": cat}):
        if x.get("name") == name:
            u = safe_uuid(x["uuid"])
            call(s, "delete", API + "services/" + u); time.sleep(0.5)
            if not gone(s, u):
                call(s, "patch", API + "services/" + u, json={"online_booking_enabled": False})
                left.append(u)
    log.append({"state": "cleanup", "name": name, "left_in_hcp": left}); save_log(run, log)
    if left:
        sys.exit(f"STOPPED: '{shown(name)}' could not be removed from HCP (id {', '.join(left)}). Online booking was "
                 f"switched off where possible. Delete it inside HCP by hand. Log: {run}")
    sys.exit(f"STOPPED: adding '{shown(name)}' failed. Nothing was left behind in HCP. Log: {run}")


def add(dry):
    todo, refused = wanted()
    for n, why in refused:
        print("REFUSED", shown(n), "-", why)
    if not todo:
        print("Nothing to add: put your price in the your_price column of missing_services.csv first."); return
    h = plan_hash(todo)
    if dry:
        json.dump({"hash": h}, open(PREVIEW_STAMP, "w"))
    else:
        if not os.path.exists(PREVIEW_STAMP) or json.load(open(PREVIEW_STAMP)).get("hash") != h:
            sys.exit("The list changed since your last preview (or there was no preview). Preview again first.")
    s = session()
    have = existing_names(s)
    run = new_run_dir("_add_preview" if dry else "_add")
    log = []
    cat = category(s, dry)
    for t in todo:
        if t["name"].lower() in have:
            print("SKIP (you already have a service with this name):", shown(t["name"])); continue
        print(("WOULD ADD " if dry else "ADD ") + f"{shown(t['name'])}  ${t['price'] / 100:,.2f}  (cost ${t['cost'] / 100:,.2f}), online booking OFF")
        if dry:
            continue
        body = dict(t, pricebook_category_uuid=cat, online_booking_enabled=False)
        entry = {"state": "attempted", "name": t["name"], "body": body}
        log.append(entry); save_log(run, log)
        try:
            r = s.post(API + "services", json=body, timeout=30)  # a create is never retried: a retry can make copies
            u = safe_uuid(unwrap(r.json())["uuid"]) if r.status_code in (200, 201) else None
        except Exception:
            u = None
        if not u:
            clean_up(s, cat, t["name"], log, run)
        entry["uuid"] = u; save_log(run, log)
        time.sleep(1)
        b = unwrap(call(s, "get", API + "services/" + u).json())
        if b.get("online_booking_enabled"):
            call(s, "patch", API + "services/" + u, json={"online_booking_enabled": False})
            b = unwrap(call(s, "get", API + "services/" + u).json())
        ok = (b.get("name") == t["name"] and b.get("price") == t["price"] and b.get("cost") == t["cost"]
              and b.get("online_booking_enabled") is False and b.get("pricebook_category_uuid") == cat)
        entry.update(state="done", ok=ok); save_log(run, log)
        if not ok:
            clean_up(s, cat, t["name"], log, run)
        have.add(t["name"].lower())
    if not dry and os.path.exists(PREVIEW_STAMP):
        os.remove(PREVIEW_STAMP)  # one preview approves one run
    print(f"\nDone. {'Previewed' if dry else 'Added'} {len(todo)} service(s) into '{CAT_NAME}'. Log: {run}")
    if dry:
        print("Looks right? Run: python pal_create.py --apply")
    else:
        print("They are NOT bookable online yet. Check them in HCP, then turn booking on yourself if you want it.")


def remove(folder, dry):
    """Delete only what one add run created, and only if it is still in our category, unchanged since."""
    folder = os.path.abspath(folder)
    logf = os.path.join(folder, "log.json")
    if not folder.rstrip("\\/").endswith("_add") or not os.path.exists(logf):
        sys.exit("That is not an add run. Pick a folder ending in _add inside backups.")
    s = session(); n = 0
    for e in json.load(open(logf)):
        u, body = e.get("uuid"), e.get("body")
        if not u or not body:
            continue
        safe_uuid(u)
        g = call(s, "get", API + "services/" + u)
        if g.status_code == 404:
            print("Already gone:", shown(e["name"])); continue
        live = unwrap(g.json())
        if live.get("pricebook_category_uuid") != body.get("pricebook_category_uuid") or live.get("name") != e["name"] \
                or live.get("price") != body.get("price") or live.get("cost") != body.get("cost"):
            print("LEFT ALONE (moved, renamed or repriced since it was added):", shown(e["name"])); continue
        print(("WOULD REMOVE " if dry else "REMOVE ") + shown(e["name"])); n += 1
        if dry:
            continue
        call(s, "delete", API + "services/" + u); time.sleep(0.5)
        if not gone(s, u):
            sys.exit(f"STOPPED: {shown(e['name'])} (id {u}) is still in HCP. Remove it there by hand.")
    print(f"\n{n} service(s) {'would be' if dry else 'were'} removed.")
    if dry and n:
        print("Looks right? Run the same command with --apply.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--remove" in a:
        remove(a[a.index("--remove") + 1], dry="--apply" not in a)
    elif "--preview" in a or "--apply" in a:
        add(dry="--apply" not in a)
    else:
        print(__doc__)
