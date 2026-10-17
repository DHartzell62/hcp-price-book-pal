"""Build the zip we hand out. Only the files listed here go in, so no price book, login or backup can leak.
Refuses to build if the test suite fails. Run: py -3 build_release.py"""
import os, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["pal.py", "pal_push.py", "pal_fix.py", "pal_library.py", "library_hvac.py", "library_plumbing.py", "library_electrical.py", "pal_create.py", "pal_vendor.py", "pal_ingest_pdf.py", "start.py", "start.bat", "requirements.txt", "README.md", "CHANGELOG.md", "LICENSE.md"]
OUT = os.path.join(os.path.dirname(HERE), "HCP_Price_Book_Pal.zip")

for t in sorted(f for f in os.listdir(HERE) if f.startswith("_test_") and f.endswith(".py")
                and not f.startswith(("_test_live", "_test_pull", "_test_push", "_test_create"))):  # offline suites only
    r = subprocess.run([sys.executable, os.path.join(HERE, t)], capture_output=True, cwd=HERE)
    if r.returncode:
        tail = (r.stdout + r.stderr).decode("utf-8", "replace").splitlines()
        print("\n".join(l for l in tail if l.startswith("FAIL") or l.startswith("      "))[:3000] or "\n".join(tail[-30:]))
        sys.exit(f"Tests failed in {t}. No release built.")
for f in FILES:
    text = open(os.path.join(HERE, f), encoding="utf-8", errors="ignore").read()
    for bad in ("olit_", "pbmat_", "_secrets", "HCP_API_KEY", "C:\\Users\\davew", "C:/Users/davew"):
        if bad in text and f != "build_release.py":
            sys.exit(f"{f} contains {bad!r}. No release built.")
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for f in FILES:
        z.write(os.path.join(HERE, f), "HCP_Price_Book_Pal/" + f)
print("Built", OUT, "with", len(FILES), "files, tests passed.")
