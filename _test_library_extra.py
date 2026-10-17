"""Offline tests for the plumbing and electrical libraries added next to library_hvac.py."""
import os, re, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pal_library, library_hvac, library_plumbing, library_electrical

ENTRIES = pal_library.ENTRIES
BAD = re.compile(r"\$|\d+ ?%|warrant|guarantee|rebate|tax credit|free of charge|—|–| - ", re.I)
EXTRA_BAD = re.compile(r"free|\bwe\b|\bour\b|\bI\b|\bus\b|\bmy\b|\bbest\b", re.I)
results = []


def test(name):
    def deco(fn):
        try:
            fn(); results.append((name, True, ""))
        except Exception:
            results.append((name, False, traceback.format_exc(limit=2)))
        return fn
    return deco


@test("combined library holds all three trades, about 60 new entries each")
def _():
    assert len(library_plumbing.ENTRIES) >= 55 and len(library_electrical.ENTRIES) >= 55
    assert len(ENTRIES) == len(library_hvac.ENTRIES) + len(library_plumbing.ENTRIES) + len(library_electrical.ENTRIES)
    assert {e["trade"] for e in ENTRIES} == {"HVAC", "Plumbing", "Electrical"}


@test("no duplicate names across the three libraries")
def _():
    names = [e["name"].lower() for e in ENTRIES]
    assert len(names) == len(set(names)), sorted(n for n in set(names) if names.count(n) > 1)


@test("new descriptions and names promise nothing: no prices, warranties, rebates, free, dashes, company voice")
def _():
    new = library_plumbing.ENTRIES + library_electrical.ENTRIES
    hits = [e["name"] for e in ENTRIES if BAD.search(e["description"]) or BAD.search(e["name"])]
    assert not [h for h in hits if h != "Free Replacement Estimate"], hits
    extra = [e["name"] for e in new if EXTRA_BAD.search(e["description"]) or EXTRA_BAD.search(e["name"])]
    assert not extra, extra
    assert all(e["description"].strip() and e["match"] for e in new)


CASES = [
    ("Kitchen Sink Drain Cleaning", "Kitchen Sink Drain Cleaning"),
    ("Toilet Fill Valve Replacement", "Toilet Fill Valve and Flapper Replacement"),
    ("Sump Pump Replacement", "Sump Pump Replacement"),
    ("Main Sewer Line Cleaning", "Main Sewer Line Cleaning"),
    ("Hose Bib Replacement", "Frost-Proof Hose Bib Replacement"),
    ("Garbage Disposal Replacement", "Garbage Disposal Replacement"),
    ("Garbage Disposal Jam", "Garbage Disposal Jam Repair"),
    ("Gas Line Leak Check", "Gas Line Pressure Test and Leak Check"),
    ("Pipe Leak Repair", "Water Line Leak Repair"),
    ("Kitchen Faucet Repair", "Faucet Repair"),
    ("Plumbing Diagnostic Service Call", "Plumbing Diagnostic Service Call"),
    ("Emergency Plumbing Call", "After-Hours Emergency Plumbing Call"),
    ("Electrical Panel Upgrade", "Electrical Panel Upgrade"),
    ("GFCI Outlet Installation", "GFCI Outlet Installation"),
    ("Light Switch Replacement", "Light Switch Replacement"),
    ("Ceiling Fan Installation", "Ceiling Fan Installation"),
    ("EV Charger Installation", "EV Charger Installation"),
    ("Whole House Surge Protector", "Whole-House Surge Protector Installation"),
    ("Smoke Detector Replacement", "Smoke Detector Replacement"),
    ("Doorbell Transformer Replacement", "Doorbell Transformer Replacement"),
    ("Circuit Breaker Replacement", "Circuit Breaker Replacement"),
    ("Recessed Lighting Installation", "Recessed Lighting Installation"),
    ("Electrical Diagnostic Service Call", "Electrical Diagnostic Service Call"),
    ("Emergency Electrician Call", "After-Hours Emergency Electrical Call"),
]


@test("realistic plumbing and electrical service names match the intended entry")
def _():
    wrong = []
    for text, want in CASES:
        e, w = pal_library.best_match(text)
        if not e or e["name"] != want:
            wrong.append((text, e["name"] if e else None, w))
    assert not wrong, wrong


@test("every new entry finds itself by its own name")
def _():
    wrong = []
    for e in library_plumbing.ENTRIES + library_electrical.ENTRIES:
        got, w = pal_library.best_match(e["name"])
        if not got or got["name"] != e["name"]:
            wrong.append((e["name"], got["name"] if got else None, w))
    assert not wrong, wrong


@test("HVAC names still match their HVAC entry, not a new one")
def _():
    for n in ("Run Capacitor Replacement", "Condensate Drain Line Clearing", "Thermostat Replacement",
              "Water Heater Flush", "Blower Motor Replacement"):
        e, w = pal_library.best_match(n)
        assert e and e["name"] == n and e["trade"] == "HVAC", (n, e and e["name"], w)


@test("every existing HVAC name still finds an HVAC entry")
def _():
    bad = []
    for e in library_hvac.ENTRIES:
        got, w = pal_library.best_match(e["name"])
        if got and got["trade"] != "HVAC":
            bad.append((e["name"], got["name"], w))
    assert not bad, bad


@test("no new match word is a single generic word that also appears in an HVAC match")
def _():
    hv = {m.lower() for e in library_hvac.ENTRIES for m in e["match"]}
    clash = [(e["name"], m) for e in library_plumbing.ENTRIES + library_electrical.ENTRIES
             for m in e["match"] if m.lower() in hv]
    assert not clash, clash


if __name__ == "__main__":
    for name, ok, err in results:
        print(("PASS " if ok else "FAIL ") + name)
        if err:
            print(err)
    print(f"{sum(1 for r in results if r[1])}/{len(results)} passed")
    sys.exit(0 if all(r[1] for r in results) else 1)
