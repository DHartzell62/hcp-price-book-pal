"""HCP Price Book Pal: suggest upfront, customer-friendly names and descriptions from the built-in library.

  python pal_library.py suggest     matches your services to the library -> suggestions.csv (writes nothing else)
  python pal_library.py accept      copies the suggestions you marked Y into pricebook.csv

How to use suggestions.csv: open it in Excel, put Y in use_name and/or use_description on the rows you
like, save, then run accept. Nothing reaches HCP until you preview and send (pal_push.py).

Careful by design:
  * a new NAME is only suggested for plain service names (no model numbers, sizes or tonnage)
  * a DESCRIPTION is only suggested where yours is empty or very short; a detailed one is never replaced
  * services only; parts and materials are left alone
"""
import csv, os, re, sys
from pal import CSV_OUT, COLS, HERE, keep_copy
from library_hvac import ENTRIES

SUGG = os.path.join(HERE, "suggestions.csv")
SCOLS = ["uuid", "current_name", "suggested_name", "use_name", "current_description",
         "suggested_description", "use_description", "matched_on"]
SHORT = 40  # a description shorter than this counts as "very short"
SPECIFIC = re.compile(r"\d|\bton\b|seer|afue|btu|model|\b[a-z]{2,}\d", re.I)


FILLER = {"the", "a", "an", "and", "of", "for", "with", "w", "standard", "std", "residential",
          "service", "call", "unit", "system", "hvac"}  # never "labor", "oem" or "only": those change the item
STEM = {"replace": "replacement", "replaced": "replacement", "replacing": "replacement", "install": "installation",
        "installed": "installation", "installing": "installation", "clean": "cleaning", "cleaned": "cleaning",
        "clear": "clearing", "cleared": "clearing", "ac": "ac", "a/c": "ac", "diag": "diagnostic"}


def words(text):
    ws = re.findall(r"[a-z0-9&/+]+", text.lower())
    return {STEM.get(w, w) for w in ws} - FILLER


def same_meaning(current, library_name):
    """True only when the library name says the same thing: no extra word in the current name (ice machine,
    geo, cleaning, water heater...) and nothing new in the library name except replacement/installation."""
    c, l = words(current), words(library_name)
    return bool(c) and not (c - l) and (l - c) <= {"replacement", "installation"}


def best_match(text):
    """Longest match word found as whole words wins, so 'dual capacitor' beats 'capacitor'."""
    flat = lambda s: " " + re.sub(r"[^a-z0-9&/+\"]+", " ", s.lower()).strip() + " "  # tune-up == tune up
    t = flat(text)
    best, word = None, ""
    for e in ENTRIES:
        for m in e["match"]:
            if flat(m) in t and len(m) > len(word):
                best, word = e, m
    return best, word


def suggest():
    rows = [r for r in csv.DictReader(open(CSV_OUT, encoding="utf-8-sig")) if r["type"] == "service"]
    out = []
    for r in rows:
        name = r["name"]
        if name.upper().startswith("ZZ"):
            continue  # retired items
        e, word = best_match(name)
        if not e:
            continue
        if SPECIFIC.search(name) or not same_meaning(name, e["name"]):
            continue  # not clearly the same job: suggest nothing rather than something wrong
        new_name = e["name"] if e["name"].lower() != name.lower() else ""
        desc = r["description"].strip()
        new_desc = e["description"] if len(desc) < SHORT else ""
        if new_name or new_desc:
            out.append({"uuid": r["uuid"], "current_name": name, "suggested_name": new_name, "use_name": "",
                        "current_description": desc, "suggested_description": new_desc, "use_description": "",
                        "matched_on": word})
    keep_copy(SUGG)
    with open(SUGG, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=SCOLS); w.writeheader(); w.writerows(out)
    names = sum(bool(x["suggested_name"]) for x in out); descs = sum(bool(x["suggested_description"]) for x in out)
    print(f"{len(out)} services have a suggestion: {names} better names, {descs} descriptions for empty or short ones.")
    print(f"Open {SUGG}, put Y in use_name / use_description on the ones you want, save, then run: python pal_library.py accept")


def accept():
    if not os.path.exists(SUGG):
        sys.exit("Run 'python pal_library.py suggest' first.")
    picks = {s["uuid"]: s for s in csv.DictReader(open(SUGG, encoding="utf-8-sig"))}
    rows = list(csv.DictReader(open(CSV_OUT, encoding="utf-8-sig")))
    n = d = 0
    for r in rows:
        s = picks.get(r["uuid"])
        if not s:
            continue
        if s["use_name"].strip().upper().startswith("Y") and s["suggested_name"]:
            r["name"] = s["suggested_name"]; n += 1
        if s["use_description"].strip().upper().startswith("Y") and s["suggested_description"]:
            r["description"] = s["suggested_description"]; d += 1
    keep_copy(CSV_OUT)
    with open(CSV_OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)
    print(f"Took {n} new names and {d} new descriptions into pricebook.csv.")
    print("Next: preview with 'python pal_push.py --preview' (menu: Preview my changes) and read every line.")


MISSING = os.path.join(HERE, "missing_services.csv")


def missing():
    """Library services your price book does not have yet, ready for you to price."""
    have = [r["name"] for r in csv.DictReader(open(CSV_OUT, encoding="utf-8-sig"))
            if r["type"] == "service" and not r["name"].upper().startswith("ZZ")]
    out = []
    for e in ENTRIES:
        if any(best_match(n)[0] is e for n in have):
            continue
        out.append({"group": e["group"], "name": e["name"], "description": e["description"], "your_price": "", "your_cost": ""})
    keep_copy(MISSING)
    with open(MISSING, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["group", "name", "description", "your_price", "your_cost"]); w.writeheader(); w.writerows(out)
    print(f"{len(out)} of {len(ENTRIES)} common services may be missing from your price book. List: {MISSING}")
    print("Check each one first: you may already have it under a different name.")
    print("Add the ones you offer inside HCP with your own prices. Want them added for you? Contact Dave Hartzell, 405-375-4822.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"suggest": suggest, "accept": accept, "missing": missing}.get(cmd, lambda: print(__doc__))()
