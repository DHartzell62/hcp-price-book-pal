"""Build the zip we hand out. Only the files listed here go in, so no price book, login or backup can leak.
Refuses to build if the test suite fails. Run: py -3 build_release.py"""
import os, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["pal.py", "pal_push.py", "pal_fix.py", "pal_library.py", "library_hvac.py", "start.py", "start.bat", "requirements.txt", "README.md", "CHANGELOG.md", "LICENSE.md"]
OUT = os.path.join(os.path.dirname(HERE), "HCP_Price_Book_Pal.zip")

if subprocess.run([sys.executable, os.path.join(HERE, "_test_suite.py")], capture_output=True).returncode:
    sys.exit("Tests failed. No release built.")
for f in FILES:
    text = open(os.path.join(HERE, f), encoding="utf-8", errors="ignore").read()
    for bad in ("olit_", "pbmat_", "_secrets", "HCP_API_KEY", "C:\\Users\\davew", "C:/Users/davew"):
        if bad in text and f != "build_release.py":
            sys.exit(f"{f} contains {bad!r}. No release built.")
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for f in FILES:
        z.write(os.path.join(HERE, f), "HCP_Price_Book_Pal/" + f)
print("Built", OUT, "with", len(FILES), "files, tests passed.")
