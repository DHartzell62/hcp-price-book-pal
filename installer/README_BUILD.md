# Building the no-Python Windows release

Build (on a machine with Python 3 and internet):

    py -3 build_exe.py

It creates a clean venv in `installer\build\venv` (only `requirements.txt` + PyInstaller, so unrelated
packages stay out), runs PyInstaller in onedir mode on `installer\launcher.py`, then copies the tool's
`.py` files (start, pal*, library_*) and docs next to the exe. Output:
`installer\dist\HCP_Price_Book_Pal\` . Zip that folder to hand out; the contractor unzips it to a
folder they can write to (NOT Program Files) and double-clicks `start.bat` or `HCP_Price_Book_Pal.exe`.

No user data is ever copied in (pricebook.csv, snapshot, backups, original_backups, spreadsheet_history,
ai_packs, .agreed, suggestions). The build aborts if any of them appear beside the exe. Data the tool
creates at run time lands beside the exe; the login profile stays in `%LOCALAPPDATA%\HCPPriceBookPal`.

## How the subprocess model works frozen

`start.py` runs `subprocess.run([sys.executable] + ["pal.py", "login"])`. Frozen, `sys.executable` is
`HCP_Price_Book_Pal.exe`, and `launcher.py` treats its first argument as a script name and runs it with
`runpy.run_path` from the exe folder (`HCP_Price_Book_Pal.exe pal.py login`). With no arguments it runs
`start.py`. So **start.py needs no change**; the existing call already works. Optional: none required.

If you ever prefer a guard, the only line that depends on this is `run()` in start.py
(`subprocess.run([sys.executable] + args, cwd=HERE)`); keep it exactly like that.

## Chromium on first run

Chromium is not bundled. The first time `pal.py login` or `pal.py pull` runs and no
`%LOCALAPPDATA%\ms-playwright\chromium-*` exists (or `PLAYWRIGHT_BROWSERS_PATH`), the launcher prints
"First run: downloading the Chromium browser (about 150 MB...)" and runs Playwright's bundled driver
`install chromium`. Manual: `HCP_Price_Book_Pal.exe --install-browser`. Needs internet once.

## Notes

- Add a new script to the tool: it is picked up automatically (`pal*.py`, `library_*.py`). A new
  dependency must be in `requirements.txt` (e.g. pdfplumber) before building.
- Unsigned exe: Windows SmartScreen or antivirus may warn on first run.
- Dist size is large mainly from Python + the Playwright driver (Node).
