"""Offline test suite: a fake HCP in memory, so every write path is exercised with zero risk.
Run: py -3 _test_suite.py   (needs no login, touches no real account)"""
import copy, csv, json, os, shutil, stat, sys, tempfile, traceback

TMP = tempfile.mkdtemp(prefix="pal_test_")
SRC = os.path.dirname(os.path.abspath(__file__))
for f in ("pal.py", "pal_push.py", "pal_fix.py", "pal_library.py", "library_hvac.py", "pal_create.py"):
    shutil.copy(os.path.join(SRC, f), TMP)
sys.path.insert(0, TMP)
import pal, pal_push, pal_fix, pal_library, library_hvac  # noqa: E402  (the copies in TMP, so files land in TMP)

BASE = pal.BASE


class Resp:
    def __init__(self, code, body=None):
        self.status_code, self._b, self.text = code, body, json.dumps(body)
    def json(self): return self._b
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


class FakeHCP:
    """services + materials in two categories; optional faults."""
    def __init__(self):
        self.items = {
            "olit_11111111111111111111111111111111": {"uuid": "olit_11111111111111111111111111111111", "name": "AC Tune-Up", "description": "Line one\r\n  indented  table", "price": 22900, "cost": 18000, "duration": 60},
            "olit_22222222222222222222222222222222": {"uuid": "olit_22222222222222222222222222222222", "name": "Furnace Check", "description": "", "price": 21000, "cost": 0, "duration": 30},
            "pbmat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": {"uuid": "pbmat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "name": "Filter 16x25", "description": "Pleated filter  ", "price": 1999, "cost": 650},
        }
        self.kind = {"olit_11111111111111111111111111111111": "service", "olit_22222222222222222222222222222222": "service", "pbmat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": "material"}
        self.ignore_patch = False
        self.patches = 0
        self.reset_on_patch = False
        self.throttle_next = 0

    def get(self, url, params=None, timeout=None):
        params = params or {}
        if self.throttle_next:
            self.throttle_next -= 1; return Resp(429, {})
        if url.endswith("/industries"):
            return Resp(200, {"data": [{"uuid": "pbind_x", "name": "HVAC"}]})
        if url.endswith("/categories") or url.endswith("/material_categories"):
            if "parent_uuid" in params:
                return Resp(200, {"data": [], "total_pages_count": 1})
            mat = url.endswith("/material_categories")
            return Resp(200, {"data": [{"uuid": "mc1" if mat else "sc1", "name": "Mats" if mat else "Svcs"}], "total_pages_count": 1})
        if url.endswith("/services"):
            return Resp(200, {"data": [copy.deepcopy(v) for k, v in self.items.items() if self.kind[k] == "service"], "total_pages_count": 1})
        if url.endswith("/materials"):
            return Resp(200, {"data": [copy.deepcopy(v) for k, v in self.items.items() if self.kind[k] == "material"], "total_pages_count": 1})
        u = url.rsplit("/", 1)[1]
        if u not in self.items:
            return Resp(404, {})
        key = "service" if self.kind[u] == "service" else "material"
        return Resp(200, {key: copy.deepcopy(self.items[u])})

    def patch(self, url, json=None, timeout=None):
        self.patches += 1
        u = url.rsplit("/", 1)[1]
        if not self.ignore_patch:
            self.items[u].update(json)
        if self.reset_on_patch:
            self.items[u]['duration'] = 0
        return Resp(200, {})


HCP = None
def fake_session(): return HCP
pal.session = pal_push.session = fake_session

results = []
def test(name):
    def deco(fn):
        global HCP
        for d in ("backups", "original_backups"):
            p = os.path.join(TMP, d)
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files: os.chmod(os.path.join(root, f), stat.S_IWRITE)
                shutil.rmtree(p)
        HCP = FakeHCP()
        try:
            fn(); results.append((name, "PASS", ""))
        except BaseException as e:
            results.append((name, "FAIL", f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=2)}"))
        return fn
    return deco


def rows(): return list(csv.DictReader(open(pal.CSV_OUT, encoding="utf-8-sig")))
def write(rs):
    with open(pal.CSV_OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=pal.COLS); w.writeheader(); w.writerows(rs)
def edit(uuid, **kw):
    rs = rows()
    for r in rs:
        if r["uuid"] == uuid: r.update(kw)
    write(rs)
def originals(): return sorted(os.listdir(pal.ORIGINALS))
def push_apply():
    pal_push.apply(*pal_push.plan(), dry=True); pal_push.apply(*pal_push.plan(), dry=False)
def add_apply():
    import pal_create
    pal_create.add(dry=True); pal_create.add(dry=False)


@test("pull writes csv, snapshot and a read-only original backup")
def _():
    pal.pull()
    assert len(rows()) == 3
    o = os.path.join(pal.ORIGINALS, originals()[0])
    for f in ("full_pricebook_from_hcp.json", "pricebook_original.csv"):
        p = os.path.join(o, f); assert os.path.exists(p)
        assert not os.access(p, os.W_OK), "original backup must be read-only"
    assert len(json.load(open(os.path.join(o, "full_pricebook_from_hcp.json")))["items"]) == 3

@test("preview writes nothing to HCP")
def _():
    pal.pull(); edit("olit_11111111111111111111111111111111", description="NEW"); pal_push.apply(*pal_push.plan(), dry=True)
    assert HCP.patches == 0 and HCP.items["olit_11111111111111111111111111111111"]["description"].startswith("Line one")

@test("apply changes only the edited field, others untouched")
def _():
    pal.pull(); before = copy.deepcopy(HCP.items["olit_11111111111111111111111111111111"])
    edit("olit_11111111111111111111111111111111", description="NEW TEXT"); push_apply()
    a = HCP.items["olit_11111111111111111111111111111111"]
    assert a["description"] == "NEW TEXT" and a["price"] == before["price"] and a["cost"] == before["cost"] and a["duration"] == 60

@test("price typed like Excel ($1,234.50) goes in as cents")
def _():
    pal.pull(); edit("pbmat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", price="$123.45"); push_apply()
    assert HCP.items["pbmat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["price"] == 12345

@test("unchanged rows produce no writes (CRLF/spacing round trip)")
def _():
    pal.pull(); assert pal_push.plan() == ([], []), pal_push.plan()

@test("item changed in HCP after the download is skipped, not overwritten")
def _():
    pal.pull(); edit("olit_11111111111111111111111111111111", description="MINE"); HCP.items["olit_11111111111111111111111111111111"]["description"] = "OFFICE CHANGED IT"
    push_apply()
    assert HCP.items["olit_11111111111111111111111111111111"]["description"] == "OFFICE CHANGED IT" and HCP.patches == 0

@test("bad readback stops the run")
def _():
    pal.pull(); edit("olit_11111111111111111111111111111111", description="A"); edit("olit_22222222222222222222222222222222", description="B"); HCP.ignore_patch = True
    try:
        push_apply(); raise AssertionError("did not stop")
    except SystemExit as e:
        assert "STOPPED" in str(e) and HCP.patches == 1, (str(e), HCP.patches)

@test("undo puts one push back")
def _():
    pal.pull(); orig = HCP.items["olit_11111111111111111111111111111111"]["description"]
    edit("olit_11111111111111111111111111111111", description="WRONG"); push_apply()
    run = [d for d in sorted(os.listdir(os.path.join(TMP, "backups"))) if not d.endswith("preview")][-1]
    pal_push.restore(os.path.join(TMP, "backups", run), dry=False, mode="undo")
    assert HCP.items["olit_11111111111111111111111111111111"]["description"].replace("\r", "") == orig.replace("\r", "")

@test("restore from original puts EVERYTHING back, including prices")
def _():
    pal.pull(); snap = copy.deepcopy(HCP.items)
    edit("olit_11111111111111111111111111111111", description="X", price="1.00"); edit("pbmat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", name="Renamed", cost="0")
    push_apply()
    HCP.items["olit_22222222222222222222222222222222"]["price"] = 5  # someone else changed it inside HCP too
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=False)
    for u in snap:
        for f in ("name", "price", "cost"):
            assert HCP.items[u][f] == snap[u][f], (u, f, HCP.items[u][f], snap[u][f])
        assert HCP.items[u]["description"].replace("\r", "") == snap[u]["description"].replace("\r", "")

@test("restore preview writes nothing")
def _():
    pal.pull(); HCP.items["olit_11111111111111111111111111111111"]["price"] = 1; n = HCP.patches
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=True)
    assert HCP.patches == n and HCP.items["olit_11111111111111111111111111111111"]["price"] == 1

@test("restore reports items deleted inside HCP instead of crashing")
def _():
    pal.pull(); del HCP.items["olit_22222222222222222222222222222222"]
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=False)

@test("restore backs up the current version first, so a restore can be undone")
def _():
    pal.pull(); HCP.items["olit_11111111111111111111111111111111"]["price"] = 1
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=False)
    runs = [d for d in os.listdir(os.path.join(TMP, "backups")) if d.endswith("_restore")]
    saved = json.load(open(os.path.join(TMP, "backups", runs[0], "olit_11111111111111111111111111111111.json")))
    assert saved["item"]["price"] == 1

@test("second download makes a second original, first one kept")
def _():
    import time
    pal.pull(); time.sleep(1.1); pal.pull(); assert len(originals()) == 2

@test("new rows and unknown types are ignored, never created")
def _():
    pal.pull(); rs = rows(); rs.append({"type": "service", "uuid": "olit_new", "category": "", "name": "N", "description": "", "price": "1", "cost": "0"}); write(rs)
    assert pal_push.plan() == ([], [])

@test("ai-merge takes descriptions only, refuses name/price changes")
def _():
    pal.pull(); pal_fix.ai_pack()
    rs = rows(); rs[0]["description"] = "AI wrote this"; rs[1]["description"] = "sneaky"; rs[1]["name"] = "renamed by AI"
    import io
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=pal.COLS); w.writeheader(); w.writerows(rs)
    open(os.path.join(pal_fix.PACKS, "pack_001_back.csv"), "w", encoding="utf-8").write("```csv\n" + buf.getvalue() + "```")
    pal_fix.ai_merge(); got = {r["uuid"]: r for r in rows()}
    assert got[rs[0]["uuid"]]["description"] == "AI wrote this"
    assert got[rs[1]["uuid"]]["description"] != "sneaky"

@test("clean keeps indents and lined-up spacing")
def _():
    pal.pull(); pal_fix.clean(); d = {r["uuid"]: r for r in rows()}["olit_11111111111111111111111111111111"]["description"]
    assert d == "Line one\n  indented  table", repr(d)

@test("Excel damage, blank price, 90% price drop, duplicate rows and date-ified names are refused")
def _():
    pal.pull(); rs = rows()
    rs[0]["description"] = "#NAME?"; rs[1]["price"] = ""; rs[2]["price"] = "0.50"
    rs.append(dict(rs[2])); rs[-1]["description"] = "dup"
    write(rs); todo, refused = pal_push.plan()
    assert todo == [] and len(refused) == 4, (todo, refused)
    edit("olit_22222222222222222222222222222222", name="10-Dec"); todo, refused = pal_push.plan(); assert todo == [] and refused, refused

@test("a write that quietly resets another field is caught and stops")
def _():
    pal.pull(); HCP.reset_on_patch = True; edit("olit_11111111111111111111111111111111", description="X")
    try:
        push_apply(); raise AssertionError("not caught")
    except SystemExit as e:
        assert "STOPPED" in str(e)

@test("HCP throttling is waited out, not a crash")
def _():
    pal.pull(); edit("olit_11111111111111111111111111111111", description="Y"); HCP.throttle_next = 1
    import pal_push as pp; old = pp.time.sleep; pp.time.sleep = lambda s: None
    try:
        push_apply()
    finally:
        pp.time.sleep = old
    assert HCP.items["olit_11111111111111111111111111111111"]["description"] == "Y"

@test("undo leaves alone anything changed again after that push")
def _():
    pal.pull(); edit("olit_11111111111111111111111111111111", description="PUSHED"); push_apply()
    HCP.items["olit_11111111111111111111111111111111"]["description"] = "OFFICE EDIT AFTER"
    run = [d for d in sorted(os.listdir(os.path.join(TMP, "backups"))) if not d.endswith("preview")][-1]
    pal_push.restore(os.path.join(TMP, "backups", run), dry=False, mode="undo")
    assert HCP.items["olit_11111111111111111111111111111111"]["description"] == "OFFICE EDIT AFTER"

@test("restore puts back exact line endings and edge spaces")
def _():
    pal.pull(); exact = HCP.items["olit_11111111111111111111111111111111"]["description"]; exact3 = HCP.items["pbmat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["description"]
    HCP.items["olit_11111111111111111111111111111111"]["description"] = "changed"; HCP.items["pbmat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["description"] = "changed"
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=False)
    assert HCP.items["olit_11111111111111111111111111111111"]["description"] == exact and HCP.items["pbmat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["description"] == exact3

@test("restore without --apply (dry) never writes")
def _():
    pal.pull(); HCP.items["olit_11111111111111111111111111111111"]["price"] = 1; n = HCP.patches
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=True); assert HCP.patches == n

@test("AI packs carry no prices or costs, and re-packing keeps the AI's answers")
def _():
    pal.pull(); pal_fix.ai_pack(); txt = open(os.path.join(pal_fix.PACKS, "pack_001.txt"), encoding="utf-8").read()
    assert "229.00" not in txt and "180.00" not in txt and ",cost" not in txt
    open(os.path.join(pal_fix.PACKS, "pack_001_back.csv"), "w").write("x"); pal_fix.ai_pack()
    assert os.path.exists(os.path.join(pal_fix.PACKS, "pack_001_back.csv"))

@test("AI merge keeps multi-line descriptions intact")
def _():
    pal.pull(); pal_fix.ai_pack(); import io
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=["uuid", "name", "description"]); w.writeheader()
    NL = chr(10)
    w.writerow({"uuid": "olit_22222222222222222222222222222222", "name": "Furnace Check", "description": "Line A" + NL + "Line B"})
    open(os.path.join(pal_fix.PACKS, "pack_001_back.csv"), "w", encoding="utf-8").write("```csv" + NL + buf.getvalue() + "```")
    pal_fix.ai_merge(); assert {r["uuid"]: r for r in rows()}["olit_22222222222222222222222222222222"]["description"] == "Line A" + NL + "Line B"

@test("downloading again keeps a copy of the old spreadsheet")
def _():
    import time
    pal.pull(); edit("olit_11111111111111111111111111111111", description="hours of work"); time.sleep(1.1); pal.pull()
    h = os.path.join(TMP, "spreadsheet_history"); got = [open(os.path.join(h, f), encoding="utf-8-sig").read() for f in os.listdir(h)]
    assert any("hours of work" in g for g in got)

@test("a full page always fetches the next page")
def _():
    big = FakeHCP(); calls = []
    def g(url, params=None, timeout=None):
        calls.append(params.get("page"))
        n = pal.PAGE if params.get("page") == 1 else 3
        return Resp(200, {"data": [{"uuid": f"u{params.get('page')}_{i}"} for i in range(n)], "total_pages_count": 1})
    big.get = g
    assert len(pal.paged(big, "x", {})) == pal.PAGE + 3 and calls == [1, 2]


@test("undo puts back the item whose write failed")
def _():
    pal.pull(); orig = HCP.items["olit_11111111111111111111111111111111"]["description"]
    edit("olit_11111111111111111111111111111111", description="HALF")
    real = pal_push.fetch; calls = {"n": 0}
    def flaky(s, kind, uuid):
        calls["n"] += 1
        it = real(s, kind, uuid)
        if calls["n"] == 2 and it:
            it = dict(it, description="garbled")  # the readback after the write looks wrong
        return it
    pal_push.apply(*pal_push.plan(), dry=True)  # preview first, with the real readback
    pal_push.fetch = flaky
    try:
        pal_push.apply(*pal_push.plan(), dry=False)
    except SystemExit:
        pass
    finally:
        pal_push.fetch = real
    run = [d for d in sorted(os.listdir(os.path.join(TMP, "backups"))) if not d.endswith("preview")][-1]
    pal_push.restore(os.path.join(TMP, "backups", run), dry=False, mode="undo")
    assert HCP.items["olit_11111111111111111111111111111111"]["description"] == orig, repr(HCP.items["olit_11111111111111111111111111111111"]["description"])

@test("undo refuses a preview folder (no record of a push)")
def _():
    pal.pull(); edit("olit_11111111111111111111111111111111", description="P"); pal_push.apply(*pal_push.plan(), dry=True)
    run = [d for d in os.listdir(os.path.join(TMP, "backups")) if d.endswith("preview")][0]
    try:
        pal_push.restore(os.path.join(TMP, "backups", run), dry=False, mode="undo"); raise AssertionError("not refused")
    except SystemExit as e:
        assert "Nothing to undo" in str(e)

@test("restore refuses a folder that is not an original download")
def _():
    pal.pull(); edit("olit_11111111111111111111111111111111", description="P"); push_apply()
    run = [d for d in os.listdir(os.path.join(TMP, "backups")) if not d.endswith("preview")][0]
    try:
        pal_push.restore(os.path.join(TMP, "backups", run), dry=False, mode="restore"); raise AssertionError("not refused")
    except SystemExit as e:
        assert "original download" in str(e)

@test("if HCP resets a field we did not send, it is put back and the run stops")
def _():
    pal.pull(); HCP.reset_on_patch = True; edit("olit_11111111111111111111111111111111", description="Z")
    real_patch = HCP.patch
    def patch_once(url, json=None, timeout=None):
        r = real_patch(url, json=json); HCP.reset_on_patch = False; return r
    HCP.patch = patch_once
    try:
        push_apply(); raise AssertionError("not stopped")
    except SystemExit:
        pass
    assert HCP.items["olit_11111111111111111111111111111111"]["duration"] == 60, HCP.items["olit_11111111111111111111111111111111"]["duration"]


@test("library renames only when the name means the same job")
def _():
    sm = pal_library.same_meaning
    assert sm("Replace Thermostat", "Thermostat Replacement")
    assert sm("Clean Flame Sensor", "Flame Sensor Cleaning")
    assert not sm("Compressor Replacement - Ice Machine", "Compressor Replacement")
    assert not sm("Contactor Replacement - Labor", "Contactor Replacement")
    assert not sm("Mini-Split Indoor Coil Cleaning", "Evaporator Coil Replacement")
    assert not sm("Gas Valve Replacement - Tank Water Heater", "Furnace Gas Valve Replacement")
    assert not sm("OEM Blower Wheel Replacement", "Blower Wheel Replacement")

@test("library descriptions promise nothing: no prices, warranties, rebates or dashes")
def _():
    import re as _re
    bad = _re.compile(r"\$|\d+ ?%|warrant|guarantee|rebate|tax credit|free of charge|—|–| - ", _re.I)
    hits = [e["name"] for e in library_hvac.ENTRIES if bad.search(e["description"]) or bad.search(e["name"])]
    assert not [h for h in hits if h != "Free Replacement Estimate"], hits
    names = [e["name"] for e in library_hvac.ENTRIES]
    assert len(names) == len(set(names)), "duplicate library names"

@test("suggest + accept: only rows marked Y change, old spreadsheet kept")
def _():
    HCP.items["olit_99999999999999999999999999999999"] = {"uuid": "olit_99999999999999999999999999999999", "name": "Replace Thermostat", "description": "", "price": 30000, "cost": 9000}
    HCP.kind["olit_99999999999999999999999999999999"] = "service"
    pal.pull(); pal_library.suggest()
    s = list(csv.DictReader(open(pal_library.SUGG, encoding="utf-8-sig")))
    row = [x for x in s if x["uuid"] == "olit_99999999999999999999999999999999"][0]
    assert row["suggested_name"] == "Thermostat Replacement" and row["suggested_description"]
    row["use_name"] = "Y"  # description left unmarked on purpose
    with open(pal_library.SUGG, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=pal_library.SCOLS); w.writeheader(); w.writerows(s)
    pal_library.accept(); got = {r["uuid"]: r for r in rows()}["olit_99999999999999999999999999999999"]
    assert got["name"] == "Thermostat Replacement" and got["description"] == "" and got["price"] == "300.00"
    todo, refused = pal_push.plan(); assert [t[1] for t in todo] == ["olit_99999999999999999999999999999999"] and list(todo[0][3]) == ["name"]

@test("missing list skips services you already have")
def _():
    pal.pull(); pal_library.missing()
    names = [r["name"] for r in csv.DictReader(open(pal_library.MISSING, encoding="utf-8-sig"))]
    assert "AC Tune-Up" not in names and "Furnace Tune-Up" not in names, names  # "Furnace Check" counts as having it
    assert "Duct Cleaning" in names


import pal_create  # noqa: E402

def creating_hcp():
    """FakeHCP that can also create and delete, and (like real HCP) makes new services bookable online."""
    h = HCP; h.cats = []
    base_get = h.get
    def get(url, params=None, timeout=None):
        params = params or {}
        if url.endswith("/categories") and params.get("id") == "_root":
            return Resp(200, {"data": [{"uuid": "sc1", "name": "Svcs"}] + h.cats, "total_pages_count": 1})
        return base_get(url, params, timeout)
    def post(url, json=None, timeout=None):
        if url.endswith("/categories"):
            c = {"uuid": f"pbcat_{len(h.cats):032x}", "name": json["name"]}; h.cats.append(c); return Resp(200, c)
        u = f"olit_ffff{len(h.items):028x}"
        h.items[u] = dict(json, uuid=u, online_booking_enabled=True); h.kind[u] = "service"
        return Resp(200, {"service": h.items[u]})
    def delete(url, timeout=None):
        u = url.rsplit("/", 1)[1]; h.items.pop(u, None); return Resp(200, {})
    h.get, h.post, h.delete = get, post, delete
    return h

def price_missing(prices):
    rs = list(csv.DictReader(open(pal_library.MISSING, encoding="utf-8-sig")))
    for r in rs:
        if r["name"] in prices: r["your_price"] = prices[r["name"]]
    with open(pal_library.MISSING, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rs[0])); w.writeheader(); w.writerows(rs)

@test("add: preview writes nothing; apply creates priced rows with online booking OFF")
def _():
    h = creating_hcp(); pal.pull(); pal_library.missing()
    price_missing({"Duct Cleaning": "$450", "UV Bulb Replacement": "abc"})
    n = len(h.items); pal_create.add(dry=True); assert len(h.items) == n
    add_apply()
    new = [v for k, v in h.items.items() if k.startswith("olit_ffff")]
    assert len(new) == 1 and new[0]["name"] == "Duct Cleaning" and new[0]["price"] == 45000, new
    assert new[0]["online_booking_enabled"] is False, "booking must be turned off"
    assert h.cats and h.cats[0]["name"] == pal_create.CAT_NAME

@test("add: a name you already have is skipped; the category is reused")
def _():
    h = creating_hcp(); pal.pull(); pal_library.missing()
    price_missing({"Duct Cleaning": "450"}); add_apply(); add_apply()
    assert sum(v["name"] == "Duct Cleaning" for v in h.items.values()) == 1 and len(h.cats) == 1

@test("remove deletes only what that add run created")
def _():
    h = creating_hcp(); pal.pull(); pal_library.missing()
    price_missing({"Duct Cleaning": "450"}); add_apply()
    run = [d for d in sorted(os.listdir(os.path.join(TMP, "backups"))) if d.endswith("_add")][-1]
    before = set(h.items); pal_create.remove(os.path.join(TMP, "backups", run), dry=True); assert set(h.items) == before
    pal_create.remove(os.path.join(TMP, "backups", run), dry=False)
    assert not [k for k in h.items if k.startswith("olit_ffff")] and "olit_11111111111111111111111111111111" in h.items


@test("Excel formula injection is neutralized in the spreadsheet and the text survives the round trip")
def _():
    evil = '=HYPERLINK("http://evil.example","click")'
    HCP.items["olit_11111111111111111111111111111111"]["description"] = evil; HCP.items["olit_22222222222222222222222222222222"]["name"] = "-Bullet style name"
    pal.pull()
    raw = open(pal.CSV_OUT, encoding="utf-8-sig").read()
    assert "'=HYPERLINK" in raw and "'-Bullet" in raw, "not defanged on disk"
    got = {r["uuid"]: r for r in pal.read_csv(pal.CSV_OUT)}
    assert got["olit_11111111111111111111111111111111"]["description"] == evil and got["olit_22222222222222222222222222222222"]["name"] == "-Bullet style name"
    assert pal_push.plan() == ([], []), "a round trip must not look like an edit"


U1 = "olit_" + "1" * 32

@test("SECURITY: a create that errors after HCP made it leaves no copy behind")
def _():
    h = creating_hcp(); pal.pull(); pal_library.missing(); price_missing({"Duct Cleaning": "450"})
    pal_create.add(dry=True)
    real_post = h.post
    def post_then_502(url, json=None, timeout=None):
        real_post(url, json=json)
        return Resp(502, {})
    h.post = lambda url, json=None, timeout=None: (Resp(200, {"uuid": "pbcat_" + "0" * 32, "name": json["name"]})
                                                  if url.endswith("/categories") else post_then_502(url, json))
    h.cats.append({"uuid": "pbcat_" + "0" * 32, "name": pal_create.CAT_NAME})
    base_get = h.get
    def get(url, params=None, timeout=None):
        if url.endswith("/services") and (params or {}).get("pricebook_category_uuid", "").startswith("pbcat_"):
            return Resp(200, {"data": [v for k, v in h.items.items() if k.startswith("olit_ffff")], "total_pages_count": 1})
        return base_get(url, params, timeout)
    h.get = get
    try:
        pal_create.add(dry=False); raise AssertionError("did not stop")
    except SystemExit as e:
        assert "Nothing was left behind" in str(e), str(e)
    assert not [k for k in h.items if k.startswith("olit_ffff")], "a copy was left in HCP"

@test("SECURITY: the list cannot change between preview and send")
def _():
    pal.pull(); edit(U1, description="PREVIEWED"); pal_push.apply(*pal_push.plan(), dry=True)
    edit(U1, description="SNUCK IN AFTER"); n = HCP.patches
    try:
        pal_push.apply(*pal_push.plan(), dry=False); raise AssertionError("not refused")
    except SystemExit as e:
        assert "Preview again" in str(e) and HCP.patches == n
    h = creating_hcp(); pal_library.missing(); price_missing({"Duct Cleaning": "450"}); pal_create.add(dry=True)
    price_missing({"Duct Cleaning": "1"})
    try:
        pal_create.add(dry=False); raise AssertionError("not refused")
    except SystemExit as e:
        assert "Preview again" in str(e)

@test("SECURITY: negative prices and 10x price jumps are refused")
def _():
    pal.pull(); edit(U1, price="-5"); assert pal_push.plan()[0] == [] and pal_push.plan()[1]
    edit(U1, price="2290.01"); assert pal_push.plan()[0] == [] and pal_push.plan()[1]
    edit(U1, price="-$-5"); assert pal_push.plan()[0] == []

@test("SECURITY: a tampered id can never reach a web address or a file name")
def _():
    pal.pull(); snap = json.load(open(pal.SNAP)); bad = "olit_x/../../evil"
    snap["rows"][bad] = dict(snap["rows"][U1], uuid=bad); json.dump(snap, open(pal.SNAP, "w"))
    rs = rows(); rs.append(dict(rs[0], uuid=bad, description="z")); write(rs)
    try:
        pal_push.plan(); raise AssertionError("bad id accepted")
    except SystemExit as e:
        assert "does not look like an HCP id" in str(e)

@test("SECURITY: remove refuses any folder that is not an add run, and leaves repriced items")
def _():
    h = creating_hcp(); pal.pull(); pal_library.missing(); price_missing({"Duct Cleaning": "450"}); add_apply()
    run = [d for d in sorted(os.listdir(os.path.join(TMP, "backups"))) if d.endswith("_add")][-1]
    other = os.path.join(TMP, "backups", "fake_push"); os.makedirs(other, exist_ok=True)
    shutil.copy(os.path.join(TMP, "backups", run, "log.json"), other)
    try:
        pal_create.remove(other, dry=False); raise AssertionError("not refused")
    except SystemExit as e:
        assert "not an add run" in str(e)
    k = [k for k in h.items if k.startswith("olit_ffff")][0]; h.items[k]["price"] = 99900
    pal_create.remove(os.path.join(TMP, "backups", run), dry=False); assert k in h.items

@test("SECURITY: login token never follows a redirect; login lives outside the tool folder")
def _():
    src = open(os.path.join(SRC, "pal.py"), encoding="utf-8").read()
    assert "s.max_redirects = 0" in src
    assert not os.path.abspath(pal.PROFILE).startswith(os.path.abspath(SRC)), pal.PROFILE

@test("paging stops if HCP repeats the same page")
def _():
    loop = FakeHCP(); loop.get = lambda url, params=None, timeout=None: Resp(200, {"data": [{"uuid": "x"}] * pal.PAGE, "total_pages_count": 99})
    assert len(pal.paged(loop, "x", {})) == pal.PAGE

@test("stale suggestions are not applied after the item changed")
def _():
    HCP.items["olit_" + "9" * 32] = {"uuid": "olit_" + "9" * 32, "name": "Replace Thermostat", "description": "", "price": 30000, "cost": 9000}
    HCP.kind["olit_" + "9" * 32] = "service"
    pal.pull(); pal_library.suggest(); s = pal.read_csv(pal_library.SUGG)
    for x in s: x["use_name"] = "Y"
    pal.write_csv(pal_library.SUGG, s, pal_library.SCOLS)
    edit("olit_" + "9" * 32, name="Thermostat Swap (renamed since)"); pal_library.accept()
    assert {r["uuid"]: r for r in rows()}["olit_" + "9" * 32]["name"] == "Thermostat Swap (renamed since)"


print()
for n, r, why in results:
    print(f"{r}  {n}")
    if why: print("      " + why.replace("\n", "\n      "))
fails = sum(r == "FAIL" for _, r, _ in results)
print(f"\n{len(results) - fails}/{len(results)} passed")
sys.exit(1 if fails else 0)
