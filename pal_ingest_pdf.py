"""Read a supplier price quote PDF into (header, rows), same shape as pal_vendor.read_sheet().

Finds the table whose header row has a part-number word and a cost word, joins multi-page tables
(repeated headers are dropped), and skips subtotal/total/tax/freight lines. Money stays TEXT
("$1,234.50"); the caller parses it. Only text that is in the PDF is returned.
"""
import re, sys

PART_WORDS = ("part", "item", "sku", "model", "catalog", "cat #", "product code", "mfr")
COST_WORDS = ("net", "your price", "cost", "dealer", "each", "unit price", "price")
SKIP = re.compile(r"^(sub\s*-?\s*total|total|grand\s+total|sales\s+tax|tax|freight|shipping|handling|"
                  r"balance(\s+due)?|amount\s+due|order\s+total|invoice\s+total|discount)\b[\s:]*", re.I)
NO_TABLE = ("No price table found in this PDF. Export the quote as Excel or CSV from the supplier "
            "site or ask your rep for one, then use that file instead.")


def _clean(c):
    return re.sub(r"\s+", " ", str(c or "")).strip()


def _is_header(row):
    low = [c.lower() for c in row]
    return any(any(w in c for w in PART_WORDS) for c in low) and any(any(w in c for w in COST_WORDS) for c in low)


def _tables(page):
    t = page.extract_tables()
    if not any(t):
        t = page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"})
    return [[[_clean(c) for c in r] for r in tb] for tb in t or []]


def read_pdf(path):
    import pdfplumber
    head, rows, text = None, [], False
    try:
        pdf = pdfplumber.open(path)
    except Exception as e:
        sys.exit(f"Could not open the PDF ({e}). Export the quote as Excel or CSV instead.")
    with pdf:
        for page in pdf.pages:
            text = text or bool((page.extract_text() or "").strip())
            for tb in _tables(page):
                for r in tb:
                    if not any(r):
                        continue
                    if head is None:
                        if _is_header(r):
                            head = r
                        continue
                    if [c.lower() for c in r] == [c.lower() for c in head]:
                        continue  # repeated header on a later page
                    if any(SKIP.match(c) for c in r if c):
                        continue
                    if len(r) < len(head):
                        r = r + [""] * (len(head) - len(r))
                    rows.append(dict(zip(head, r, strict=False)))
    if head is None or not rows:
        sys.exit(NO_TABLE if text else "This PDF is a scanned picture with no readable text. " + NO_TABLE)
    return head, rows


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python pal_ingest_pdf.py quote.pdf")
    h, rs = read_pdf(sys.argv[1])
    print(h)
    for r in rs[:10]:
        print(r)
