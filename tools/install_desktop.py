#!/usr/bin/env python3
"""Install/uninstall only SnapMark's launcher and icon, without root privileges."""
import argparse
import os
from pathlib import Path
import shutil
import sys


def quote_exec(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))))
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    prefix = args.prefix.expanduser().resolve()
    desktop = prefix / "applications" / "io.github.snapmark.SnapMark.desktop"
    icon = prefix / "icons" / "hicolor" / "scalable" / "apps" / "io.github.snapmark.SnapMark.svg"
    legacy_desktop = prefix / "applications" / "io.github.cpp.Screenshot.desktop"
    legacy_icon = prefix / "icons" / "hicolor" / "scalable" / "apps" / "io.github.cpp.Screenshot.svg"
    if args.uninstall:
        desktop.unlink(missing_ok=True)
        icon.unlink(missing_ok=True)
        legacy_desktop.unlink(missing_ok=True)
        legacy_icon.unlink(missing_ok=True)
        print("Removed SnapMark desktop launcher and icon. Images and settings were preserved.")
        return
    from cpp import __file__ as package_file
    source_icon = Path(package_file).parent / "assets" / "snapmark.svg"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_icon, icon)
    command = quote_exec(sys.executable) + " -m cpp"
    desktop.write_text("[Desktop Entry]\nType=Application\nVersion=1.0\nName=SnapMark\n"
        "Comment=Capture screenshots and annotate images locally\n"
        f"Exec={command} %f\nIcon=io.github.snapmark.SnapMark\nTerminal=false\n"
        "Categories=Graphics;Qt;\nMimeType=image/png;image/jpeg;image/webp;\n"
        "StartupNotify=true\nActions=Full;Region;\n\n"
        f"[Desktop Action Full]\nName=Capture Full Screen\nExec={command} --capture full\n\n"
        f"[Desktop Action Region]\nName=Capture Region\nExec={command} --capture region\n")
    # Retire only this application's known pre-rename desktop identity.
    legacy_desktop.unlink(missing_ok=True)
    legacy_icon.unlink(missing_ok=True)
    print(f"Installed {desktop}")


if __name__ == "__main__":
    main()
