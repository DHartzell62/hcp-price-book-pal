"""Frozen launcher for HCP Price Book Pal (PyInstaller entry point).

  launcher.exe                    -> the guided menu (start.py)
  launcher.exe pal.py login       -> runs that script with those args (what start.py's subprocess calls need)
  launcher.exe --install-browser  -> downloads Chromium for Playwright (also done automatically on first need)

Scripts live as plain .py files beside this exe, so user data (pricebook.csv, backups) is written there too.
"""
import glob, os, runpy, subprocess, sys

APP = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
NEEDS_BROWSER = {("pal.py", "login"), ("pal.py", "pull")}


def browsers_dir():
    return os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ms-playwright")


def browser_installed():
    return bool(glob.glob(os.path.join(browsers_dir(), "chromium-*")))


def install_browser():
    print("\n  First run: downloading the Chromium browser (about 150 MB, one time only).")
    print("  This needs internet and can take a few minutes. Please wait...\n", flush=True)
    from playwright._impl._driver import compute_driver_executable, get_driver_env
    drv = compute_driver_executable()
    cmd = list(drv) if isinstance(drv, (tuple, list)) else [str(drv)]
    r = subprocess.run(cmd + ["install", "chromium"], env=get_driver_env())
    if r.returncode:
        print("\n  The browser download failed. Check your internet and run this again.")
    else:
        print("\n  Browser ready.")
    return r.returncode


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--install-browser":
        sys.exit(install_browser())
    script = argv[0] if argv else "start.py"
    rest = argv[1:]
    path = script if os.path.isabs(script) else os.path.join(APP, script)
    if not os.path.isfile(path):
        sys.exit(f"Unknown script: {script}")
    if (os.path.basename(path), rest[0] if rest else "") in NEEDS_BROWSER and not browser_installed():
        if install_browser():
            sys.exit(1)
    os.chdir(APP)
    sys.path.insert(0, APP)
    sys.argv = [path] + rest
    runpy.run_path(path, run_name="__main__")


if __name__ == "__main__":
    main()
