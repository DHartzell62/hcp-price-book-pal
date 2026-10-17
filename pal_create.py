"""HCP Price Book Pal: add the missing services you priced.

  python pal_create.py --preview            shows what would be added, writes nothing
  python pal_create.py --apply              adds them to HCP
  python pal_create.py --remove <folder>    preview removing the services one add run created
  python pal_create.py --remove <folder> --apply

Fill in your_price (and your_cost if you track it) in missing_services.csv. Only rows with a price are added.
Every new service goes into one category, "Added by Price Book Pal", with ONLINE BOOKING OFF (HCP turns it
on by default for new services; this tool turns it off and checks). Turn booking on yourself in HCP when the
price is final. Each run is logged so it can be removed again.
"""
import csv, json, os, sys, time
from datetime import datetime
from pal import BASE, HERE, session, paged
from pal_push import cents, call, save_log
from pal_library import MISSING

CAT_NAME = "Added by Price Book Pal"
API = BASE + "/"


def unwrap(j):
    for k in ("service", "category"):
        if isinstance(j, dict) and k in j:
            return j[k]
    return j


def wanted():
    if not os.path.exists(MISSING):
        sys.exit("Run the missing-services step first (python pal_library.py missing).")
    out, refused, seen = [], [], set()
    for r in csv.DictReader(open(MISSING, encoding="utf-8-sig")):
        if not (r.get("your_price") or "").strip():
            continue
        p, c = cents(r["your_price"]), cents(r.get("your_cost") or "0")
        name = (r.get("name") or "").strip()
        if p is None or c is None:
            refused.append((name, "price or cost is not a plain dollar amount")); continue
        if not name or name.lower() in seen:
            refused.append((name, "blank or duplicate name")); continue
        seen.add(name.lower())
        out.append({"name": name, "description": r.get("description") or "", "price": p, "cost": c,
                    "taxable": (r.get("taxable") or "").strip().upper().startswith("Y")})
    return out, refused


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
    r = call(s, "post", API + "categories", json={"name": CAT_NAME, "pricebook_industry_uuid": ind})
    r.raise_for_status()
    return unwrap(r.json())["uuid"]


def add(dry):
    todo, refused = wanted()
    for n, why in refused:
        print("REFUSED", n, "-", why)
    if not todo:
        print("Nothing to add: put your price in the your_price column of missing_services.csv first."); return
    s = session()
    have = existing_names(s)
    run = os.path.join(HERE, "backups", datetime.now().strftime("%Y%m%d_%H%M%S") + ("_add_preview" if dry else "_add"))
    os.makedirs(run); log = []
    cat = category(s, dry)
    for t in todo:
        if t["name"].lower() in have:
            print("SKIP (you already have a service with this name):", t["name"]); continue
        print(("WOULD ADD " if dry else "ADD ") + f"{t['name']}  ${t['price'] / 100:,.2f}  (cost ${t['cost'] / 100:,.2f}), online booking OFF")
        if dry:
            continue
        body = dict(t, pricebook_category_uuid=cat, online_booking_enabled=False)
        entry = {"state": "attempted", "name": t["name"], "body": body}
        log.append(entry); save_log(run, log)
        r = call(s, "post", API + "services", json=body)
        if r.status_code not in (200, 201):
            sys.exit(f"STOPPED: HCP refused {t['name']} ({r.status_code}). Log: {run}")
        new = unwrap(r.json()); entry["uuid"] = new["uuid"]; save_log(run, log)
        time.sleep(1)
        b = unwrap(call(s, "get", API + "services/" + new["uuid"]).json())
        if b.get("online_booking_enabled"):
            call(s, "patch", API + "services/" + new["uuid"], json={"online_booking_enabled": False})
            b = unwrap(call(s, "get", API + "services/" + new["uuid"]).json())
        ok = (b.get("name") == t["name"] and b.get("price") == t["price"] and b.get("cost") == t["cost"]
              and b.get("online_booking_enabled") is False and b.get("pricebook_category_uuid") == cat)
        entry.update(state="done", ok=ok); save_log(run, log)
        if not ok:
            call(s, "delete", API + "services/" + new["uuid"])
            sys.exit(f"STOPPED: {t['name']} did not read back right, so it was removed again. Log: {run}")
        have.add(t["name"].lower())
    print(f"\nDone. {'Previewed' if dry else 'Added'} {len(todo)} service(s) into '{CAT_NAME}'. Log: {run}")
    if dry:
        print("Looks right? Run: python pal_create.py --apply")
    else:
        print("They are NOT bookable online yet. Check them in HCP, then turn booking on yourself if you want it.")


def remove(folder, dry):
    logf = os.path.join(folder, "log.json")
    if not os.path.exists(logf):
        sys.exit("That folder has no record of an add run. Pick a folder ending in _add inside backups.")
    s = session(); n = 0
    for e in json.load(open(logf)):
        u = e.get("uuid")
        if not u:
            continue
        g = call(s, "get", API + "services/" + u)
        if g.status_code == 404:
            print("Already gone:", e["name"]); continue
        print(("WOULD REMOVE " if dry else "REMOVE ") + e["name"]); n += 1
        if dry:
            continue
        call(s, "delete", API + "services/" + u); time.sleep(0.5)
        if call(s, "get", API + "services/" + u).status_code != 404:
            sys.exit(f"STOPPED: {e['name']} is still in HCP. Remove it there by hand.")
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
