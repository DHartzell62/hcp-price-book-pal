"""HCP Price Book Pal: push your edited pricebook.csv back into Housecall Pro.

  python pal_push.py --preview                  shows every change, writes nothing
  python pal_push.py --apply                    makes the changes shown in the preview
  python pal_push.py --undo <folder> [--apply]  reverses one push (backups/<date>); preview unless --apply
  python pal_push.py --restore <folder> [--apply]
        puts EVERY item back the way it was in an original download (original_backups/<date>);
        preview unless --apply

Safety, every time:
  * only rows you changed (name, description, price, cost) are touched, nothing else
  * rows that look damaged by Excel, have a blank price, or drop a price by over 90% are refused
  * if HCP changed since your last download, that row is skipped, never overwritten
  * the full item is backed up before each change, and the WHOLE item is read back after
  * stops at the first thing that does not read back right
"""
import csv, json, os, re, sys, time
from datetime import datetime
from pal import BASE, CSV_OUT, SNAP, HERE, session, read_csv, safe_uuid, shown, new_run_dir
import hashlib

FIELDS = ["name", "description", "price", "cost"]
URL = {"service": f"{BASE}/services/", "material": f"{BASE}/materials/"}
EXCEL_ERRORS = ("#NAME?", "#VALUE!", "#REF!", "#N/A", "#DIV/0!", "#NUM!", "#NULL!")
MONEY = re.compile(r"^\$?((\d{1,3}(,\d{3})+|\d+)(\.\d{1,2})?|\.\d{1,2})$")  # no negatives, no stray signs
DATEISH = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$|^\d{1,2}-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$", re.I)


def cents(v):
    """Dollars as typed (1234.5, $1,234.50) -> cents. None if it is not a plain dollar amount."""
    t = str(v).strip()
    if not t or not MONEY.match(t) or t in ("$", "-", "."):
        return None
    return int(round(float(t.replace("$", "").replace(",", "")) * 100))


def same(field, a, b):
    if field in ("price", "cost"):
        return cents(a) == cents(b)
    return (a or "").replace("\r", "").strip() == (b or "").replace("\r", "").strip()


def live_row(item):
    return {"name": item.get("name") or "", "description": (item.get("description") or "").replace("\r", ""),
            "price": f"{(item.get('price') or 0) / 100:.2f}", "cost": f"{(item.get('cost') or 0) / 100:.2f}"}


def body_for(changes):
    return {f: (cents(v) if f in ("price", "cost") else v) for f, v in changes.items()}


def call(s, method, url, **kw):
    """One HCP request, waiting and retrying when HCP throttles or hiccups."""
    for i in range(4):
        r = getattr(s, method)(url, timeout=30, **kw)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 * (i + 1)); continue
        return r
    return r


def fetch(s, kind, uuid):
    r = call(s, "get", URL[kind] + uuid)
    if r.status_code == 404:
        return None
    r.raise_for_status(); j = r.json()
    return j.get("service") or j.get("material") or j


def norm(v):
    """For comparing a whole item: ignore timestamps and the signature part of image links."""
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items() if "updated" not in k and k not in ("created_at",)}
    if isinstance(v, list):
        return [norm(x) for x in v]
    if isinstance(v, str) and "X-Amz-" in v:
        return v.split("?")[0]
    if isinstance(v, str):
        return v.replace("\r", "")
    return v


def rest_unchanged(before, after, edited):
    """Every field we did NOT send must be exactly as it was."""
    b, a = norm(before), norm(after)
    return all(a.get(k) == b.get(k) for k in b if k not in edited)


def save_log(run, log):
    json.dump(log, open(os.path.join(run, "log.json"), "w"), indent=1)


def repair(s, kind, uuid, before, after, edited):
    """HCP changed a field we did not send. Put those fields back from the backup and say so."""
    b, a = norm(before), norm(after)
    fix = {k: before[k] for k in b if k not in edited and a.get(k) != b.get(k)}
    if not fix:
        return
    r = call(s, "patch", URL[kind] + uuid, json=fix)
    again = norm(fetch(s, kind, uuid) or {})
    left = [k for k in fix if again.get(k) != b.get(k)]
    print(f"    HCP changed {', '.join(fix)} on its own. Put back: {'all of it' if not left else 'NOT ' + ', '.join(left)}"
          f" (status {r.status_code}). Check this item in HCP.")


def refuse_reason(field, new, old):
    if any(e in (new or "") for e in EXCEL_ERRORS):
        return "looks damaged by Excel (" + shown(new[:20]) + ")"
    if field in ("price", "cost"):
        c = cents(new)
        if c is None:
            return f"{field} {new!r} is not a plain dollar amount"
        if field == "price" and cents(old) and c > cents(old) * 10:
            return f"price jumps more than 10 times ({old} -> {new}), check for a typo or change it inside HCP"
        if field == "price" and cents(old) and c < cents(old) * 0.10:
            return f"price drops over 90% ({old} -> {new}), fix it or change it inside HCP"
    if field == "name" and DATEISH.match((new or "").strip()):
        return f"name {new!r} looks like Excel turned it into a date"
    if field == "description" and len(new or "") >= 32767:
        return "description hit Excel's length limit and was cut off"
    return None


def plan():
    if not os.path.exists(SNAP):
        sys.exit("Run 'python pal.py pull' first.")
    snap = json.load(open(SNAP, encoding="utf-8"))["rows"]
    todo, refused, seen = [], [], set()
    for r in read_csv(CSV_OUT):
        u = r.get("uuid", "")
        if u and u in snap:
            safe_uuid(u)
        old = snap.get(u)
        if not old or r.get("type") not in URL:
            continue  # new or unknown rows are ignored: this tool edits, it never creates
        if u in seen:
            refused.append((old["name"], "this item appears twice in the spreadsheet")); continue
        seen.add(u)
        ch = {f: r[f] for f in FIELDS if f in r and not same(f, r[f], old[f])}
        bad = [refuse_reason(f, v, old[f]) for f, v in ch.items()]
        bad = [b for b in bad if b]
        if bad:
            refused.append((old["name"], "; ".join(bad))); continue
        if ch:
            todo.append((r["type"], u, old, ch))
    return todo, refused


def show(f, a, b):
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    st = max(0, i - 25)
    print(f"    {f}: ...{a[st:i + 45]!r} -> ...{b[st:i + 45]!r}" if i > 25 else f"    {f}: {a[:70]!r} -> {b[:70]!r}")


def apply(todo, refused, dry):
    for name, why in refused:
        print("REFUSED", shown(name), "-", why)
    h = hashlib.sha256(json.dumps([[k, u, c] for k, u, _, c in todo], sort_keys=True).encode()).hexdigest()
    stamp = os.path.join(HERE, ".push_preview.json")
    if dry and os.path.exists(stamp):
        os.remove(stamp)  # written again only when this preview finishes cleanly
    if not dry and (not os.path.exists(stamp) or json.load(open(stamp)).get("hash") != h):
        sys.exit("Your spreadsheet changed since your last preview (or there was no preview). Preview again first.")
    run = new_run_dir("_preview" if dry else "")
    s = session(); log = []
    for kind, uuid, old, ch in todo:
        live = fetch(s, kind, uuid)
        if live is None:
            print("GONE from HCP, skipped:", shown(old["name"])); continue
        json.dump({"type": kind, "item": live}, open(os.path.join(run, uuid + ".json"), "x", encoding="utf-8"), ensure_ascii=True)
        lr = live_row(live)
        if any(not same(f, lr[f], old[f]) for f in ch):
            print("SKIP (changed in HCP since your download):", shown(old["name"])); log.append({"uuid": uuid, "result": "skipped"}); continue
        print(("WOULD CHANGE " if dry else "CHANGE ") + shown(old["name"]))
        for f, v in ch.items():
            show(f, old[f], v)
        if dry:
            continue
        body = body_for(ch)
        entry = {"uuid": uuid, "type": kind, "state": "attempted", "ok": False, "wrote": body}
        log.append(entry); save_log(run, log)  # recorded BEFORE the write, so a crash mid-write can still be undone
        r = call(s, "patch", URL[kind] + uuid, json=body)
        time.sleep(1)
        after = fetch(s, kind, uuid) or {}
        ok = r.status_code in (200, 204) and all(same(f, live_row(after)[f], v) for f, v in ch.items())
        if ok and not rest_unchanged(live, after, ch):
            ok = False; repair(s, kind, uuid, live, after, ch)
        entry.update(state="done", status=r.status_code, ok=ok); save_log(run, log)
        if not ok:
            sys.exit(f"STOPPED: {shown(old['name'])} did not read back right. Its old version is saved in {run}. "
                     f"Undo this push from the menu (Undo one push) to put it back.")
    if dry:
        json.dump({"hash": h}, open(stamp, "w"))
    elif os.path.exists(stamp):
        os.remove(stamp)  # one preview approves one send
    print(f"\n{len(todo)} item(s) {'previewed' if dry else 'processed'}, {len(refused)} refused. Backups: {run}")
    if dry and todo:
        print("Looks right? Run: python pal_push.py --apply")


def saved_items(folder):
    """Items saved in an original download folder, or in one push's backup folder."""
    full = os.path.join(folder, "full_pricebook_from_hcp.json")
    if os.path.exists(full):
        return [(x["type"], x["item"]) for x in json.load(open(full, encoding="utf-8"))["items"]]
    out = []
    for fn in sorted(os.listdir(folder)):
        if fn.endswith(".json") and fn != "log.json":
            b = json.load(open(os.path.join(folder, fn), encoding="utf-8")); out.append((b["type"], b["item"]))
    return out


def raw4(item):
    return {"name": item.get("name") or "", "description": item.get("description") or "",
            "price": item.get("price") or 0, "cost": item.get("cost") or 0}


def restore(folder, dry, mode="restore"):
    """Put back name, description, price and cost exactly as saved. The current HCP version of each item is
    backed up first, so a restore can itself be undone. Undoing a push only touches items that push wrote
    (or tried to write); a finished item that was changed again after the push is left alone."""
    if not os.path.isdir(folder):
        sys.exit(f"Folder not found: {folder}")
    logf = os.path.join(folder, "log.json")
    wrote, failed = {}, set()
    if mode == "undo":
        if not os.path.exists(logf):
            sys.exit("That folder has no record of a push (a preview, or a push where nothing was written). "
                     "Nothing to undo. To put everything back, use the original_backups restore instead.")
        for x in json.load(open(logf)):
            if x.get("wrote"):
                wrote[x["uuid"]] = x["wrote"]
                if not x.get("ok"):
                    failed.add(x["uuid"])  # the write that went wrong is exactly the one to put back
        items = [(k, it) for k, it in saved_items(folder) if it["uuid"] in wrote]
    else:
        if not os.path.exists(os.path.join(folder, "full_pricebook_from_hcp.json")):
            sys.exit("That is not an original download folder. Pick one inside original_backups.")
        items = saved_items(folder)
    run = new_run_dir("_restore_preview" if dry else "_restore")
    s = session(); n = gone = later = 0; log = []
    for kind, it in items:
        safe_uuid(it.get("uuid"))
        want = raw4(it)
        live = fetch(s, kind, it["uuid"])
        if live is None:
            gone += 1; print("GONE from HCP (deleted there, this tool cannot re-create it):", shown(want["name"])); continue
        cur = raw4(live)
        if it["uuid"] in wrote and it["uuid"] not in failed and any(norm(cur[f]) != norm(v) for f, v in wrote[it["uuid"]].items()):
            later += 1; print("SKIP (changed again after that push, left alone):", shown(want["name"])); continue
        diff = {f: want[f] for f in FIELDS if cur[f] != want[f]}
        if not diff:
            continue
        n += 1
        print(("WOULD RESTORE " if dry else "RESTORE ") + shown(want["name"]), "(" + ", ".join(diff) + ")")
        if dry:
            continue
        json.dump({"type": kind, "item": live}, open(os.path.join(run, it["uuid"] + ".json"), "x", encoding="utf-8"), ensure_ascii=True)
        entry = {"uuid": it["uuid"], "type": kind, "state": "attempted", "ok": False, "wrote": diff}
        log.append(entry); save_log(run, log)
        p = call(s, "patch", URL[kind] + it["uuid"], json=diff)
        time.sleep(1)
        after = fetch(s, kind, it["uuid"]) or {}
        ok = p.status_code in (200, 204) and all(norm(raw4(after)[f]) == norm(v) for f, v in diff.items())
        if ok and not rest_unchanged(live, after, diff):
            ok = False; repair(s, kind, it["uuid"], live, after, diff)
        entry.update(state="done", status=p.status_code, ok=ok); save_log(run, log)
        if not ok:
            sys.exit(f"STOPPED: {want['name']} did not read back right. Its current version is saved in {run}")
    print()
    print(f"{n} item(s) {'would be' if dry else 'were'} restored. {gone} gone from HCP. {later} changed later and left alone.")
    if dry and n:
        print("Looks right? Run the same command with --apply.")
    if gone:
        print("Items deleted inside HCP have to be re-added by hand. Need help? Call Dave Hartzell, 405-375-4822.")


def main():
    a = sys.argv[1:]
    if "--undo" in a or "--restore" in a:
        flag = "--undo" if "--undo" in a else "--restore"
        restore(a[a.index(flag) + 1], dry="--apply" not in a, mode=flag[2:])
    elif "--preview" not in a and "--apply" not in a:
        print(__doc__)
    else:
        t, refused = plan()
        if not t and not refused:
            print("No changes found between pricebook.csv and your last download.")
        else:
            apply(t, refused, dry="--apply" not in a)


if __name__ == "__main__":
    from pal import friendly
    friendly(main)
