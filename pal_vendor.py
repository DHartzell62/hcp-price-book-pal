"""HCP Price Book Pal: feed a supplier price sheet and get proposed cost and price updates.

  python pal_vendor.py match [price_sheet.csv, .xlsx or .pdf] [--part-col "Item #"] [--cost-col "Net"]
        with no file, reads the newest sheet in the inbox folder (the ingestion inbox)
        matches the sheet to your parts by part number -> vendor_updates.csv (writes nothing else)
  python pal_vendor.py accept
        copies the rows you marked Y into pricebook.csv, then preview and send as usual

vendor_updates.csv shows, for every matched part: your current cost, the supplier's cost, the change, your
current price, and a suggested price that KEEPS YOUR CURRENT MARKUP (same price-to-cost ratio). Put Y in
use_cost and/or use_price on the rows you want. Big changes are flagged "check units" because suppliers
sometimes price by the box or the foot. Parts on the sheet that you do not carry are listed in
vendor_not_in_pricebook.csv. Nothing reaches HCP until you preview and send.
"""
import os, re, sys
from pal import CSV_OUT, COLS, HERE, keep_copy, read_csv, write_csv, shown

UPD = os.path.join(HERE, "vendor_updates.csv")
NOTIN = os.path.join(HERE, "vendor_not_in_pricebook.csv")
UCOLS = ["uuid", "name", "part_number", "current_cost", "vendor_cost", "change_pct", "current_price",
         "suggested_price", "use_cost", "use_price", "note"]
PART_WORDS = ("part", "item", "sku", "model", "catalog", "cat #", "product code", "mfr")
COST_WORDS = ("net", "your price", "cost", "dealer", "each", "unit price", "price")


def norm_part(p):
    return re.sub(r"[^A-Z0-9]", "", str(p or "").upper())


def money(v):
    """A plain dollar amount (digits, commas, one decimal point) or None. No 1e9, inf or negatives."""
    t = re.sub(r"[$\s]", "", str(v or ""))
    if not re.fullmatch(r"(\d{1,3}(,\d{3})+|\d+)(\.\d+)?|\.\d+", t):
        return None
    return round(float(t.replace(",", "")), 2)


NOT_COST = ("list", "msrp", "retail", "suggested", "ext", "total", "qty", "quantity")   # never the cost column
NOT_PART = ("description", "desc", "name", "qty", "quantity", "uom")                   # never the part column
MAX_FILE_MB, MAX_UNZIPPED_MB, MAX_ROWS, MAX_PDF_PAGES = 25, 200, 100000, 200


INBOX = os.path.join(HERE, "inbox")
SHEET_TYPES = (".csv", ".xlsx", ".xlsm", ".pdf")


def newest_in_inbox():
    """The ingestion inbox: drop supplier price sheets here; the newest one is read."""
    os.makedirs(INBOX, exist_ok=True)
    files = [os.path.join(INBOX, f) for f in os.listdir(INBOX) if f.lower().endswith(SHEET_TYPES)]
    if not files:
        sys.exit(f"The inbox is empty. Put a supplier price sheet (Excel, CSV or PDF) in {INBOX} and try again.")
    return max(files, key=os.path.getmtime)


def is_header(row):
    low = [c.lower() for c in row]
    return (any(any(w in c for w in PART_WORDS) and not any(n in c for n in NOT_PART) for c in low)
            and any(any(w in c for w in COST_WORDS) and not any(n in c for n in NOT_COST) for c in low))


def tables(grid):
    """Split one grid into (header, rows) tables: every header row starts a new table, so tabs or sections
    laid out differently are each read against their OWN headings."""
    out, head = [], None
    for row in grid:
        if is_header(row):
            head = row; out.append((head, [])); continue
        if head and any(row):
            out[-1][1].append(dict(zip(head, row, strict=False)))  # short or long rows are allowed here
    return out


def check_size(path):
    if os.path.getsize(path) > MAX_FILE_MB * 1024 * 1024:
        sys.exit(f"That file is over {MAX_FILE_MB} MB. Save just the price list part of it and try again.")
    if path.lower().endswith((".xlsx", ".xlsm")):
        import zipfile
        with zipfile.ZipFile(path) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED_MB * 1024 * 1024:
                sys.exit("That Excel file unpacks to something enormous. Refusing to open it.")


def read_sheet(path):
    """Tables of (header, rows) from a CSV, Excel or PDF price sheet."""
    check_size(path)
    if path.lower().endswith(".pdf"):
        try:
            import pdfplumber
            from pal_ingest_pdf import read_pdf
        except ImportError:
            sys.exit("PDF reading is not installed in this version. Export the quote as Excel or CSV instead.")
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) > MAX_PDF_PAGES:
                sys.exit(f"That PDF has over {MAX_PDF_PAGES} pages. Export the price list as Excel or CSV instead.")
        head, rows = read_pdf(path)
        rows = [r for r in rows if len([v for v in r.values() if v is not None]) == len(head)]  # no shifted rows
        return [(head, rows)], True
    grid = []
    if path.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl  # data_only: formulas and macros are never run, only their saved values read
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                grid.append([("" if c is None else str(c)).strip() for c in row])
                if len(grid) > MAX_ROWS:
                    sys.exit(f"That sheet has over {MAX_ROWS:,} rows. Save just the price list and try again.")
            grid.append([])
    else:
        import csv
        for row in csv.reader(open(path, encoding="utf-8-sig", errors="replace")):
            grid.append([c.strip() for c in row])
            if len(grid) > MAX_ROWS:
                sys.exit(f"That sheet has over {MAX_ROWS:,} rows. Save just the price list and try again.")
    found = tables(grid)
    if not found:
        sys.exit("Could not find a header row with a part number column and a cost column. "
                 "Use --part-col and --cost-col with the exact column names.")
    return found, False


def pick(head, words, banned, given):
    if given:
        return given if given in head else None
    for w in words:  # words are in order of preference
        for h in head:
            hl = h.lower()
            if w in hl and not any(b in hl for b in banned):
                return h
    return None


def arg(name):
    a = sys.argv
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else None


def match(sheet):
    found, from_pdf = read_sheet(sheet)
    vendor, dupes, sample = {}, set(), []
    for head, lines in found:
        pcol = pick(head, PART_WORDS, NOT_PART, arg("--part-col"))
        ccol = pick(head, COST_WORDS, NOT_COST, arg("--cost-col"))
        if not pcol or not ccol:
            continue
        print(f"Table with {len(lines)} lines: part number column '{shown(pcol)}', cost column '{shown(ccol)}'.")
        for ln in lines:
            k, c = norm_part(ln.get(pcol)), money(ln.get(ccol))
            if not k or c is None:
                continue
            if k in vendor and vendor[k][1] != c:
                dupes.add(k)  # the sheet lists this part twice at different costs (each vs case?)
            vendor.setdefault(k, (ln.get(pcol), c))
            if len(sample) < 3:
                sample.append(f"{shown(ln.get(pcol))} = ${c:,.2f}")
    if not vendor:
        sys.exit("No part number + cost pairs found. Use --part-col and --cost-col with the exact column names.")
    print("First lines read:", "; ".join(sample), "(if these look wrong, stop and use --part-col / --cost-col)")
    mats = [r for r in read_csv(CSV_OUT) if r["type"] == "material" and norm_part(r.get("part_number"))]
    if not mats:
        sys.exit("None of your parts have a part number in HCP, so nothing can be matched. Download again with this version first.")
    costs_by_part = {}
    for r in mats:
        costs_by_part.setdefault(norm_part(r["part_number"]), set()).add(f"{money(r['cost']) or 0:.2f}")
    out, used = [], set()
    for r in mats:
        k = norm_part(r["part_number"])
        if k not in vendor:
            continue
        used.add(k)
        shared = len(costs_by_part[k]) > 1  # one part number on several items with different costs
        old_c, old_p, new_c = money(r["cost"]) or 0.0, money(r["price"]) or 0.0, vendor[k][1]
        if round(old_c, 2) == new_c:
            continue
        chg = ((new_c - old_c) / old_c * 100) if old_c else None
        sug = round(old_p * new_c / old_c, 2) if old_c and old_p else ""
        note = []
        if from_pdf:
            note.append("read from a PDF: verify against the quote")
        if k in dupes:
            note.append("the sheet lists this part more than once at different costs (each vs case?)")
        if len(k) < 4:
            note.append("very short part number: make sure it is the same part")
        if shared:
            note.append("this part number is on several of your items with different costs (a model family or kit?): check each one")
        if chg is not None and abs(chg) > 50:
            note.append("check units (box vs each, per foot)")
        if not old_c:
            note.append("you had no cost; set your own price")
        out.append({"uuid": r["uuid"], "name": r["name"], "part_number": r["part_number"],
                    "current_cost": f"{old_c:.2f}", "vendor_cost": f"{new_c:.2f}",
                    "change_pct": "" if chg is None else f"{chg:+.1f}%", "current_price": f"{old_p:.2f}",
                    "suggested_price": "" if sug == "" else f"{sug:.2f}", "use_cost": "", "use_price": "",
                    "note": "; ".join(note)})
    out.sort(key=lambda x: -abs(float(x["change_pct"].rstrip("%") or 0)) if x["change_pct"] else 0)
    keep_copy(UPD); write_csv(UPD, out, UCOLS)
    notin = [{"part_number": v[0], "vendor_cost": f"{v[1]:.2f}"} for k, v in vendor.items() if k not in used]
    write_csv(NOTIN, notin, ["part_number", "vendor_cost"])
    up = sum(1 for x in out if x["change_pct"].startswith("+")); down = sum(1 for x in out if x["change_pct"].startswith("-"))
    flagged = sum(1 for x in out if x["note"])
    print(f"{len(vendor)} priced lines on the sheet. {len(used)} of them match part numbers in your price book, "
          f"covering {len(out)} of your items with a new cost ({up} up, {down} down). "
          f"{flagged} are flagged to check first. {len(notin)} sheet lines are parts you do not carry.")
    print(f"Open {UPD}, put Y in use_cost / use_price on the rows you want, save, then run: python pal_vendor.py accept")


def accept():
    if not os.path.exists(UPD):
        sys.exit("Run 'python pal_vendor.py match <sheet>' first.")
    picks = {u["uuid"]: u for u in read_csv(UPD)}
    rows = read_csv(CSV_OUT)
    c = p = held = 0
    for r in rows:
        u = picks.get(r["uuid"])
        if not u or u["current_cost"] != f"{money(r['cost']) or 0:.2f}" or u["current_price"] != f"{money(r['price']) or 0:.2f}":
            continue  # missing, or the item's cost or price changed since the match: run match again
        # A flagged row (units, shared part number, PDF, duplicate line) needs YES typed out, not just Y.
        flagged = bool(u["note"].strip())
        def ok(v, flagged=flagged):
            v = v.strip().upper()
            return v == "YES" or (not flagged and v.startswith("Y"))
        for col in ("use_cost", "use_price"):
            if u[col].strip() and not ok(u[col]):
                held += 1
        if ok(u["use_cost"]):
            r["cost"] = u["vendor_cost"]; c += 1
        if ok(u["use_price"]) and u["suggested_price"]:
            r["price"] = u["suggested_price"]; p += 1
    keep_copy(CSV_OUT); write_csv(CSV_OUT, rows, COLS)
    print(f"Took {c} new costs and {p} new prices into pricebook.csv.")
    if held:
        print(f"{held} marked row(s) were NOT taken: rows with a note need YES typed out after you check them.")
    print("Next: preview with 'python pal_push.py --preview' (menu: Preview my changes) and read every line.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "match":
        sheet = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else newest_in_inbox()
        print("Reading", shown(os.path.basename(sheet)))
        match(sheet)
    elif len(sys.argv) > 1 and sys.argv[1] == "accept":
        accept()
    else:
        print(__doc__)
