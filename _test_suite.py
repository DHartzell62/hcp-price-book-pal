"""Offline test suite: a fake HCP in memory, so every write path is exercised with zero risk.
Run: py -3 _test_suite.py   (needs no login, touches no real account)"""
import copy, csv, json, os, shutil, stat, sys, tempfile, traceback

TMP = tempfile.mkdtemp(prefix="pal_test_")
SRC = os.path.dirname(os.path.abspath(__file__))
for f in ("pal.py", "pal_push.py", "pal_fix.py"):
    shutil.copy(os.path.join(SRC, f), TMP)
sys.path.insert(0, TMP)
import pal, pal_push, pal_fix  # noqa: E402  (the copies in TMP, so files land in TMP)

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
            "olit_1": {"uuid": "olit_1", "name": "AC Tune-Up", "description": "Line one\r\n  indented  table", "price": 22900, "cost": 18000, "duration": 60},
            "olit_2": {"uuid": "olit_2", "name": "Furnace Check", "description": "", "price": 21000, "cost": 0, "duration": 30},
            "pbmat_1": {"uuid": "pbmat_1", "name": "Filter 16x25", "description": "Pleated filter  ", "price": 1999, "cost": 650},
        }
        self.kind = {"olit_1": "service", "olit_2": "service", "pbmat_1": "material"}
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
    pal.pull(); edit("olit_1", description="NEW"); pal_push.apply(*pal_push.plan(), dry=True)
    assert HCP.patches == 0 and HCP.items["olit_1"]["description"].startswith("Line one")

@test("apply changes only the edited field, others untouched")
def _():
    pal.pull(); before = copy.deepcopy(HCP.items["olit_1"])
    edit("olit_1", description="NEW TEXT"); pal_push.apply(*pal_push.plan(), dry=False)
    a = HCP.items["olit_1"]
    assert a["description"] == "NEW TEXT" and a["price"] == before["price"] and a["cost"] == before["cost"] and a["duration"] == 60

@test("price typed like Excel ($1,234.50) goes in as cents")
def _():
    pal.pull(); edit("pbmat_1", price="$1,234.50"); pal_push.apply(*pal_push.plan(), dry=False)
    assert HCP.items["pbmat_1"]["price"] == 123450

@test("unchanged rows produce no writes (CRLF/spacing round trip)")
def _():
    pal.pull(); assert pal_push.plan() == ([], []), pal_push.plan()

@test("item changed in HCP after the download is skipped, not overwritten")
def _():
    pal.pull(); edit("olit_1", description="MINE"); HCP.items["olit_1"]["description"] = "OFFICE CHANGED IT"
    pal_push.apply(*pal_push.plan(), dry=False)
    assert HCP.items["olit_1"]["description"] == "OFFICE CHANGED IT" and HCP.patches == 0

@test("bad readback stops the run")
def _():
    pal.pull(); edit("olit_1", description="A"); edit("olit_2", description="B"); HCP.ignore_patch = True
    try:
        pal_push.apply(*pal_push.plan(), dry=False); raise AssertionError("did not stop")
    except SystemExit as e:
        assert "STOPPED" in str(e) and HCP.patches == 1, (str(e), HCP.patches)

@test("undo puts one push back")
def _():
    pal.pull(); orig = HCP.items["olit_1"]["description"]
    edit("olit_1", description="WRONG"); pal_push.apply(*pal_push.plan(), dry=False)
    run = [d for d in sorted(os.listdir(os.path.join(TMP, "backups"))) if not d.endswith("preview")][-1]
    pal_push.restore(os.path.join(TMP, "backups", run), dry=False, mode="undo")
    assert HCP.items["olit_1"]["description"].replace("\r", "") == orig.replace("\r", "")

@test("restore from original puts EVERYTHING back, including prices")
def _():
    pal.pull(); snap = copy.deepcopy(HCP.items)
    edit("olit_1", description="X", price="1.00"); edit("pbmat_1", name="Renamed", cost="0")
    pal_push.apply(*pal_push.plan(), dry=False)
    HCP.items["olit_2"]["price"] = 5  # someone else changed it inside HCP too
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=False)
    for u in snap:
        for f in ("name", "price", "cost"):
            assert HCP.items[u][f] == snap[u][f], (u, f, HCP.items[u][f], snap[u][f])
        assert HCP.items[u]["description"].replace("\r", "") == snap[u]["description"].replace("\r", "")

@test("restore preview writes nothing")
def _():
    pal.pull(); HCP.items["olit_1"]["price"] = 1; n = HCP.patches
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=True)
    assert HCP.patches == n and HCP.items["olit_1"]["price"] == 1

@test("restore reports items deleted inside HCP instead of crashing")
def _():
    pal.pull(); del HCP.items["olit_2"]
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=False)

@test("restore backs up the current version first, so a restore can be undone")
def _():
    pal.pull(); HCP.items["olit_1"]["price"] = 1
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=False)
    runs = [d for d in os.listdir(os.path.join(TMP, "backups")) if d.endswith("_restore")]
    saved = json.load(open(os.path.join(TMP, "backups", runs[0], "olit_1.json")))
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
    pal.pull(); pal_fix.clean(); d = {r["uuid"]: r for r in rows()}["olit_1"]["description"]
    assert d == "Line one\n  indented  table", repr(d)

@test("Excel damage, blank price, 90% price drop, duplicate rows and date-ified names are refused")
def _():
    pal.pull(); rs = rows()
    rs[0]["description"] = "#NAME?"; rs[1]["price"] = ""; rs[2]["price"] = "0.50"
    rs.append(dict(rs[2])); rs[-1]["description"] = "dup"
    write(rs); todo, refused = pal_push.plan()
    assert todo == [] and len(refused) == 4, (todo, refused)
    edit("olit_2", name="10-Dec"); todo, refused = pal_push.plan(); assert todo == [] and refused, refused

@test("a write that quietly resets another field is caught and stops")
def _():
    pal.pull(); HCP.reset_on_patch = True; edit("olit_1", description="X")
    try:
        pal_push.apply(*pal_push.plan(), dry=False); raise AssertionError("not caught")
    except SystemExit as e:
        assert "STOPPED" in str(e)

@test("HCP throttling is waited out, not a crash")
def _():
    pal.pull(); edit("olit_1", description="Y"); HCP.throttle_next = 1
    import pal_push as pp; old = pp.time.sleep; pp.time.sleep = lambda s: None
    try:
        pal_push.apply(*pal_push.plan(), dry=False)
    finally:
        pp.time.sleep = old
    assert HCP.items["olit_1"]["description"] == "Y"

@test("undo leaves alone anything changed again after that push")
def _():
    pal.pull(); edit("olit_1", description="PUSHED"); pal_push.apply(*pal_push.plan(), dry=False)
    HCP.items["olit_1"]["description"] = "OFFICE EDIT AFTER"
    run = [d for d in sorted(os.listdir(os.path.join(TMP, "backups"))) if not d.endswith("preview")][-1]
    pal_push.restore(os.path.join(TMP, "backups", run), dry=False, mode="undo")
    assert HCP.items["olit_1"]["description"] == "OFFICE EDIT AFTER"

@test("restore puts back exact line endings and edge spaces")
def _():
    pal.pull(); exact = HCP.items["olit_1"]["description"]; exact3 = HCP.items["pbmat_1"]["description"]
    HCP.items["olit_1"]["description"] = "changed"; HCP.items["pbmat_1"]["description"] = "changed"
    pal_push.restore(os.path.join(pal.ORIGINALS, originals()[0]), dry=False)
    assert HCP.items["olit_1"]["description"] == exact and HCP.items["pbmat_1"]["description"] == exact3

@test("restore without --apply (dry) never writes")
def _():
    pal.pull(); HCP.items["olit_1"]["price"] = 1; n = HCP.patches
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
    w.writerow({"uuid": "olit_2", "name": "Furnace Check", "description": "Line A" + NL + "Line B"})
    open(os.path.join(pal_fix.PACKS, "pack_001_back.csv"), "w", encoding="utf-8").write("```csv" + NL + buf.getvalue() + "```")
    pal_fix.ai_merge(); assert {r["uuid"]: r for r in rows()}["olit_2"]["description"] == "Line A" + NL + "Line B"

@test("downloading again keeps a copy of the old spreadsheet")
def _():
    import time
    pal.pull(); edit("olit_1", description="hours of work"); time.sleep(1.1); pal.pull()
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
    pal.pull(); orig = HCP.items["olit_1"]["description"]
    edit("olit_1", description="HALF")
    real = pal_push.fetch; calls = {"n": 0}
    def flaky(s, kind, uuid):
        calls["n"] += 1
        it = real(s, kind, uuid)
        if calls["n"] == 2 and it:
            it = dict(it, description="garbled")  # the readback after the write looks wrong
        return it
    pal_push.fetch = flaky
    try:
        pal_push.apply(*pal_push.plan(), dry=False)
    except SystemExit:
        pass
    finally:
        pal_push.fetch = real
    run = [d for d in sorted(os.listdir(os.path.join(TMP, "backups"))) if not d.endswith("preview")][-1]
    pal_push.restore(os.path.join(TMP, "backups", run), dry=False, mode="undo")
    assert HCP.items["olit_1"]["description"] == orig, repr(HCP.items["olit_1"]["description"])

@test("undo refuses a preview folder (no record of a push)")
def _():
    pal.pull(); edit("olit_1", description="P"); pal_push.apply(*pal_push.plan(), dry=True)
    run = [d for d in os.listdir(os.path.join(TMP, "backups")) if d.endswith("preview")][0]
    try:
        pal_push.restore(os.path.join(TMP, "backups", run), dry=False, mode="undo"); raise AssertionError("not refused")
    except SystemExit as e:
        assert "Nothing to undo" in str(e)

@test("restore refuses a folder that is not an original download")
def _():
    pal.pull(); edit("olit_1", description="P"); pal_push.apply(*pal_push.plan(), dry=False)
    run = [d for d in os.listdir(os.path.join(TMP, "backups")) if not d.endswith("preview")][0]
    try:
        pal_push.restore(os.path.join(TMP, "backups", run), dry=False, mode="restore"); raise AssertionError("not refused")
    except SystemExit as e:
        assert "original download" in str(e)

@test("if HCP resets a field we did not send, it is put back and the run stops")
def _():
    pal.pull(); HCP.reset_on_patch = True; edit("olit_1", description="Z")
    real_patch = HCP.patch
    def patch_once(url, json=None, timeout=None):
        r = real_patch(url, json=json); HCP.reset_on_patch = False; return r
    HCP.patch = patch_once
    try:
        pal_push.apply(*pal_push.plan(), dry=False); raise AssertionError("not stopped")
    except SystemExit:
        pass
    assert HCP.items["olit_1"]["duration"] == 60, HCP.items["olit_1"]["duration"]


print()
for n, r, why in results:
    print(f"{r}  {n}")
    if why: print("      " + why.replace("\n", "\n      "))
fails = sum(r == "FAIL" for _, r, _ in results)
print(f"\n{len(results) - fails}/{len(results)} passed")
sys.exit(1 if fails else 0)
