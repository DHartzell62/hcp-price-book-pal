"""Offline tests for pal_ingest_pdf. Run: py -3 _test_pdf.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from pal_ingest_pdf import read_pdf

HDR = ["Item #", "Description", "Qty", "Unit Price", "Ext"]
GRID = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)])


def build(path, blocks):
    story = []
    for b in blocks:
        story.append(b if not isinstance(b, list) else Table(b, style=GRID))
    SimpleDocTemplate(path, pagesize=letter).build(story)


d = tempfile.mkdtemp()
# 1. simple one page
p1 = os.path.join(d, "one.pdf")
r1 = [["CA-1234", "Run capacitor 35/5", "2", "$12.50", "$25.00"], ["MC-77", "Contactor 2P 30A", "1", "$1,234.50", "$1,234.50"]]
build(p1, [HDR] and [[HDR] + r1])
h, rows = read_pdf(p1)
assert h == HDR, h
assert rows == [dict(zip(HDR, r, strict=True)) for r in r1], rows
# 2. two pages, repeated header, total rows
p2 = os.path.join(d, "two.pdf")
a = [["A-%d" % i, "Part %d" % i, "1", "$%d.00" % i, "$%d.00" % i] for i in range(1, 3)]
b = [["B-%d" % i, "Part B%d" % i, "3", "$%d.25" % i, "$%d.75" % i] for i in range(1, 3)]
build(p2, [[HDR] + a, PageBreak(), [HDR] + b + [["", "Subtotal", "", "", "$99.00"], ["", "Freight", "", "", "$5.00"],
                                               ["", "Total", "", "", "$104.00"]]])
h, rows = read_pdf(p2)
assert h == HDR
assert rows == [dict(zip(HDR, r, strict=True)) for r in a + b], rows
assert not any("otal" in str(v) for r in rows for v in r.values())
# 3. no table
p3 = os.path.join(d, "none.pdf")
build(p3, [Paragraph("Thanks for your business. Call us with questions about your order.", getSampleStyleSheet()["Normal"])])
try:
    read_pdf(p3)
    raise AssertionError("expected SystemExit")
except SystemExit as e:
    assert "Excel or CSV" in str(e.code), e.code
print("ALL PDF TESTS PASSED")
