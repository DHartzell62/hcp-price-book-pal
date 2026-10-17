"""HCP Price Book Pal: the guided menu. Double-click start.bat, or run: python start.py"""
import os, subprocess, sys, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
DAVE = "Dave Hartzell, Hartzell's Heat & Air, Kingfisher OK: call 405-375-4822"

STEPS = [
    ("Log into Housecall Pro", ["pal.py", "login"],
     "A browser opens on HCP's own login page. Your password goes to HCP, never to this tool. "
     "Do this once; run it again if the tool ever says your login expired."),
    ("Download my price book", ["pal.py", "pull"],
     "Saves every service and material to pricebook.csv, which opens in Excel. Takes a few minutes. "
     "Recommendation: download fresh right before you edit, so nobody's changes get stepped on."),
    ("Clean up descriptions (automatic)", ["pal_fix.py", "clean"],
     "Fixes garbled characters, trailing spaces and extra blank lines; your spacing and tables are kept. Nothing goes to HCP yet. "
     "Recommendation: always run this first, it is safe and quick."),
    ("Suggest better names and descriptions (built-in library)", ["pal_library.py", "suggest"],
     "Matches your services to a library of clear, customer-friendly upfront names and descriptions. "
     "A new name is only suggested when it means exactly the same job, and a description only where yours "
     "is empty or very short. Sends nothing to HCP. Recommendation: open suggestions.csv and put Y only on "
     "the ones you like."),
    ("Take the suggestions I marked Y", ["pal_library.py", "accept"],
     "Copies the suggestions you marked Y into pricebook.csv. Your old spreadsheet is saved first."),
    ("Show common services I may be missing", ["pal_library.py", "missing"],
     "Lists common HVAC and water heater services from the library that are not in your price book, with "
     "descriptions ready to use. Check each one, you may have it under another name. Put your own price in "
     "the your_price column on the ones you offer."),
    ("Add the missing services I priced", ["pal_create.py", "--apply"],
     "Adds every row of missing_services.csv that has a price, into one category called 'Added by Price Book "
     "Pal'. You see the preview first. They are added with online booking OFF, so customers cannot book them "
     "until you turn it on in HCP. Each add is logged and can be removed again."),
    ("Remove services I added", "remove",
     "Deletes the services one add run created, nothing else. Pick that run's folder (it ends in _add inside "
     "backups). You see a preview first."),
    ("Rewrite descriptions with ChatGPT or Claude", ["pal_fix.py", "ai-pack"],
     "Makes small paste-ready files in the ai_packs folder. Paste one into a free ChatGPT or Claude chat, "
     "save its answer as pack_001_back.csv, and so on. Recommendation: start with one pack and read the "
     "results before doing the rest."),
    ("Bring the AI's rewrites back in", ["pal_fix.py", "ai-merge"],
     "Reads the _back.csv files into pricebook.csv. If the AI changed a name or a price, that row is "
     "refused: only descriptions are taken."),
    ("Preview my changes (writes nothing)", ["pal_push.py", "--preview"],
     "Shows every item you changed, old and new. Nothing is written to HCP. "
     "Recommendation: read the whole preview. Prices you edit by hand in Excel show up here too."),
    ("Send my changes to Housecall Pro", ["pal_push.py", "--apply"],
     "Shows the preview again, then writes the changes when you type YES. Each item is backed up first and checked after. "
     "Recommendation: try it on a few items first, then check them in HCP."),
    ("Undo one push", "undo",
     "Puts back the values from one push's backup folder (backups/<date>). You see a preview first. "
     "Recommendation: use this when one push went wrong and you want just that one reversed."),
    ("Put EVERYTHING back the way it was", "restore",
     "Every download saves a permanent, read-only copy of your whole price book in original_backups/<date>. "
     "This puts every item back to that copy: name, description, price and cost. You see a preview first. "
     "Items deleted inside HCP cannot be re-created by this tool."),
]


def bubble(text, title="TIP"):
    w = 72
    lines = textwrap.wrap(text, w - 4)
    print("  +" + "-" * (w - 2) + "+")
    print("  | " + title.ljust(w - 4) + " |")
    for l in lines:
        print("  | " + l.ljust(w - 4) + " |")
    print("  +" + "-" * (w - 2) + "+")


def contact():
    bubble("This tool downloads your price book, cleans and rewrites descriptions, and pushes your "
           "edits back with a backup. Anything else, like bulk price increases by formula, matching "
           "vendor price sheets, new items, estimate templates, or a question about how to set it up: "
           f"contact {DAVE}.", "NEED SOMETHING ELSE?")


def run(args):
    r = subprocess.run([sys.executable] + args, cwd=HERE)
    if r.returncode:
        bubble(f"That step stopped with a problem. Read the message above. Stuck? {DAVE}.", "HELP")
    return r.returncode == 0


def preview_then_confirm(preview_args, real_args):
    """Always show the preview first; only a clean preview plus a typed YES does the real thing."""
    if not run(preview_args):
        print("  The preview had a problem, so nothing was changed."); return
    if input("  That was the preview. Type YES to send it to Housecall Pro: ").strip() != "YES":
        print("  Cancelled, nothing changed."); return
    run(real_args)


AGREEMENT = ("This tool is free and comes with no warranty. You use it at your own risk and you are "
             "responsible for your Housecall Pro account and your prices. Hartzell's Heat & Air and Dave "
             "Hartzell are not responsible for any change, loss or problem. Every download saves an "
             "original backup, and every change is backed up first, but check your price book in HCP after.")


def agreed():
    flag = os.path.join(HERE, ".agreed")
    if os.path.exists(flag):
        return True
    bubble(AGREEMENT, "BEFORE YOU START")
    if input("  Type I AGREE to continue: ").strip().upper() != "I AGREE":
        print("  OK, nothing was done."); return False
    open(flag, "w").write("agreed"); return True


def main():
    if not agreed():
        return
    print("\n  HCP PRICE BOOK PAL v1.2 Basic   free from Hartzell's Heat & Air")
    bubble("Work top to bottom: log in, download, clean, (rewrite with AI), preview, send. "
           "Nothing reaches Housecall Pro until you pick 'Send my changes' and type YES. Every download saves a permanent original backup, and every change is backed up first. "
           "This uses the same private connection HCP's own website uses; it is not an HCP product.",
           "START HERE")
    while True:
        print()
        for i, (name, _, _) in enumerate(STEPS, 1):
            print(f"   {i}. {name}")
        print(f"   {len(STEPS) + 1}. Help / contact Dave")
        print("   0. Quit")
        c = input("\n  Pick a number: ").strip()
        if c == "0":
            return
        if c == str(len(STEPS) + 1):
            contact(); continue
        if not c.isdigit() or not 1 <= int(c) <= len(STEPS):
            bubble("Type one of the numbers in the list.", "HELP"); continue
        name, args, tip = STEPS[int(c) - 1]
        bubble(tip, name.upper())
        if args in ("undo", "restore", "remove"):
            where = "original_backups" if args == "restore" else "backups"
            folder = input(f"  Paste the folder to restore (it is inside {where}): ").strip().strip('"')
            if not os.path.isdir(os.path.join(HERE, folder)) and not os.path.isdir(folder):
                bubble(f"That folder was not found. Look inside the {where} folder next to this tool.", "HELP"); continue
            folder = folder if os.path.isdir(folder) else os.path.join(HERE, folder)
            base = (["pal_create.py"] if args == "remove" else ["pal_push.py"]) + ["--" + args, folder]
            preview_then_confirm(base, base + ["--apply"]); continue
        if args[-1] == "--apply":
            preview_then_confirm(args[:-1] + ["--preview"], args); continue
        run(args)


if __name__ == "__main__":
    main()
