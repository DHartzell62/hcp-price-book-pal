"""Build a no-Python Windows copy of HCP Price Book Pal (PyInstaller, onedir).
Run: py -3 build_exe.py     Output: installer\dist\HCP_Price_Book_Pal\ (zip that folder to hand out)
Only the files in SCRIPTS/DOCS are copied in, so no price book, backup, snapshot or login can leak."""
import ast, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
INST = os.path.join(HERE, "installer")
DIST, WORK = os.path.join(INST, "dist"), os.path.join(INST, "build")
NAME = "HCP_Price_Book_Pal"
import glob
SCRIPTS = sorted({"start.py"} | {os.path.basename(p) for p in glob.glob(os.path.join(HERE, "pal*.py"))
                                 + glob.glob(os.path.join(HERE, "library_*.py"))})
DOCS = ["README.md", "CHANGELOG.md", "LICENSE.md", "requirements.txt"]
LOCAL = {s[:-3] for s in SCRIPTS}
FORBIDDEN = ("pricebook.csv", "pricebook_snapshot.json", "backups", "original_backups", "spreadsheet_history",
             "ai_packs", ".agreed", "suggestions.csv", "missing_services.csv")


def imports_of(path):
    mods = set()
    for n in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            mods.add(n.module.split(".")[0])
    return mods


def make_venv():
    """Clean venv with only requirements.txt + pyinstaller, so this machine's other packages (torch, cv2...) stay out."""
    venv = os.path.join(WORK, "venv")
    py = os.path.join(venv, "Scripts", "python.exe")
    if not os.path.isfile(py):
        subprocess.check_call([sys.executable, "-m", "venv", venv])
        subprocess.check_call([py, "-m", "pip", "install", "-q", "-r", os.path.join(HERE, "requirements.txt"), "pyinstaller"])
    return py


def main():
    scripts = [s for s in SCRIPTS if os.path.isfile(os.path.join(HERE, s))]
    hidden = set()
    for s in scripts:
        hidden |= imports_of(os.path.join(HERE, s))
    hidden -= LOCAL
    hidden |= {"requests", "openpyxl", "playwright", "playwright.sync_api"}
    if os.path.isfile(os.path.join(HERE, "installer", "launcher.py")) is False:
        sys.exit("installer\launcher.py missing")
    py = make_venv()
    cmd = [py, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
           "--name", NAME, "--distpath", DIST, "--workpath", WORK, "--specpath", WORK,
           "--collect-all", "playwright", "--collect-all", "certifi"]
    for m in sorted(hidden):
        cmd += ["--hidden-import", m]
    if "pdfplumber" in hidden:
        cmd += ["--collect-all", "pdfplumber", "--collect-all", "pdfminer"]
    cmd.append(os.path.join(INST, "launcher.py"))
    print(" ".join(cmd))
    if subprocess.run(cmd).returncode:
        sys.exit("PyInstaller failed")
    out = os.path.join(DIST, NAME)
    for f in scripts + [d for d in DOCS if os.path.isfile(os.path.join(HERE, d))]:
        shutil.copy2(os.path.join(HERE, f), out)
    with open(os.path.join(out, "start.bat"), "w") as f:
        f.write('@echo off\r\ncd /d "%~dp0"\r\n"%~dp0' + NAME + '.exe"\r\npause\r\n')
    for bad in FORBIDDEN:  # belt and braces: nothing user-owned may be in the output
        for root, dirs, files in os.walk(out):
            if bad in dirs + files and root.startswith(out) and "_internal" not in root:
                sys.exit(f"Refusing: {bad} found in build at {root}")
    total = sum(os.path.getsize(os.path.join(r, x)) for r, _, fs in os.walk(out) for x in fs)
    print(f"Built {out}  ({total/1048576:.0f} MB)")


if __name__ == "__main__":
    main()
