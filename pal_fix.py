"""HCP Price Book Pal: correct your descriptions.

  python pal_fix.py clean          fixes garbled characters, trailing spaces and extra blank lines
                                   in pricebook.csv, and counts items with no description
  python pal_fix.py ai-pack        makes paste-ready files in ai_packs/ for ChatGPT or Claude
  python pal_fix.py ai-merge       reads the files the AI gave back (ai_packs/*_back.csv) into pricebook.csv

Nothing here touches HCP. You review pricebook.csv, then pal_push.py previews and applies.
"""
import csv, glob, io, os, re, sys
from pal import CSV_OUT, COLS, HERE, keep_copy

PACKS = os.path.join(HERE, "ai_packs")
CHUNK = 60  # rows per AI pack, small enough for a free ChatGPT/Claude chat
PACK_COLS = ["uuid", "name", "description"]  # no prices or costs ever go to the AI
MOJIBAKE = {"â€™": "'", "â€˜": "'", "â€œ": '"', "â€\u009d": '"',
            "â€”": "-", "â€“": "-", "Â ": " ", "Â": "", "�": "-"}

PROMPT = """You are cleaning up a Housecall Pro price book for a home service company.
Below is a CSV. For EVERY row, rewrite only the "description" column so a homeowner understands it:
- plain words, short sentences, say what the job includes
- fix spelling and grammar
- keep every real fact: prices, warranty terms, model numbers, sizes, what is included or excluded
- never invent a warranty, guarantee, discount, rebate or tax credit that is not already written there
- if a description is empty, write 1-2 sentences from the item name only, no promises
Do NOT change the uuid or name columns. Return the SAME rows in the SAME
order as a CSV with the same header, inside one code block, and nothing else.
"""


def load():
    return list(csv.DictReader(open(CSV_OUT, encoding="utf-8-sig")))


def save(rows, path=CSV_OUT):
    keep_copy(path)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)


def tidy(t):
    for bad, good in MOJIBAKE.items():
        t = t.replace(bad, good)
    t = t.replace("\r", "")
    t = re.sub(r"[ \t]+\n", "\n", t)  # trailing spaces at line ends; indents and lined-up tables kept
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip("\n").rstrip()


def clean():
    rows = load(); fixed = empty = 0
    for r in rows:
        new = tidy(r["description"])
        if new != r["description"]:
            r["description"] = new; fixed += 1
        if not new:
            empty += 1
    save(rows)
    print(f"Cleaned {fixed} descriptions. {empty} items have NO description.")
    print("Next: 'python pal_fix.py ai-pack' to have ChatGPT or Claude rewrite them, or review pricebook.csv.")


def ai_pack():
    rows = load(); os.makedirs(PACKS, exist_ok=True)
    for old in glob.glob(os.path.join(PACKS, "pack_[0-9][0-9][0-9].txt")):
        os.remove(old)
    n = 0
    for i in range(0, len(rows), CHUNK):
        n += 1
        part = rows[i:i + CHUNK]
        path = os.path.join(PACKS, f"pack_{n:03d}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(PROMPT + "\n```csv\n")
            w = csv.DictWriter(f, fieldnames=PACK_COLS, extrasaction="ignore"); w.writeheader(); w.writerows(part)
            f.write("```\n")
    print(f"Made {n} packs in {PACKS}.")
    print("For each pack: paste the whole file into ChatGPT or Claude, copy the CSV it returns,")
    print("save it as the same name ending _back.csv (pack_001_back.csv), then run 'python pal_fix.py ai-merge'.")


def ai_merge():
    rows = load(); by = {r["uuid"]: r for r in rows}; took = refused = 0
    for path in sorted(glob.glob(os.path.join(PACKS, "*_back.csv"))):
        text = open(path, encoding="utf-8-sig").read()
        text = re.sub(r"^```[a-z]*\n|```\s*$", "", text.strip(), flags=re.M)
        for r in csv.DictReader(io.StringIO(text)):
            old = by.get(r.get("uuid", ""))
            if not old:
                continue
            # the AI may only change the description; anything else changed means the row is refused
            if any((r.get(c) or "").strip() != (old[c] or "").strip() for c in ("name",)):
                refused += 1; continue
            new = tidy(r.get("description") or "")
            if new and new != old["description"]:
                old["description"] = new; took += 1
    save(rows)
    print(f"Took {took} new description(s). Refused {refused} rows where the AI changed a name.")
    print("Next: open pricebook.csv and read them, then 'python pal_push.py --preview'.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"clean": clean, "ai-pack": ai_pack, "ai-merge": ai_merge}.get(cmd, lambda: print(__doc__))()
