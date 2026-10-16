#!/usr/bin/env python3
"""Build a self-contained Ubuntu .deb with the current Python environment."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def main():
    if platform.system() != "Linux":
        raise SystemExit("Build on Ubuntu Linux, on the oldest release you intend to support.")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    arch = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    libc = platform.libc_ver()[1]
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    artifact = output / f"snapmark_{version}_{arch}.deb"
    with tempfile.TemporaryDirectory(prefix="snapmark-release-") as temp:
        work = Path(temp)
        run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
            "--name", "snapmark", "--paths", ROOT / "src",
            "--add-data", f"{ROOT / 'src/cpp/assets'}:cpp/assets",
            "--collect-submodules", "dbus_next", "--collect-submodules", "Xlib",
            "--distpath", work / "dist", "--workpath", work / "build",
            "--specpath", work, ROOT / "src/cpp/__main__.py")
        stage = work / "package"
        app = stage / "opt/snapmark"
        shutil.copytree(work / "dist/snapmark", app)
        bindir = stage / "usr/bin"
        bindir.mkdir(parents=True)
        (bindir / "snapmark").symlink_to("/opt/snapmark/snapmark")
        for source, destination in [
            (ROOT / "packaging/io.github.snapmark.SnapMark.desktop", "usr/share/applications/io.github.snapmark.SnapMark.desktop"),
            (ROOT / "src/cpp/assets/snapmark.svg", "usr/share/icons/hicolor/scalable/apps/io.github.snapmark.SnapMark.svg"),
            (ROOT / "LICENSE", "usr/share/doc/snapmark/copyright"),
        ]:
            target = stage / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        notices = stage / "usr/share/doc/snapmark/third-party"
        notices.mkdir(parents=True)
        packages = ["PySide6-Essentials", "shiboken6", "Pillow", "dbus-next", "python-xlib", "six"]
        manifest = {"version": version, "architecture": arch, "build_os": platform.freedesktop_os_release(),
                    "glibc_minimum": libc, "python": sys.version, "dependencies": {}}
        for name in packages:
            dist = importlib.metadata.distribution(name)
            manifest["dependencies"][name] = dist.version
            for file in dist.files or []:
                if any(part.lower().startswith(("license", "copying", "notice")) for part in file.parts):
                    source = Path(dist.locate_file(file))
                    if source.is_file():
                        target = notices / name / file
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
        (stage / "usr/share/doc/snapmark/build.json").write_text(json.dumps(manifest, indent=2) + "\n")
        control = stage / "DEBIAN"
        control.mkdir()
        size = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file()) // 1024
        (control / "control").write_text(f"""Package: snapmark
Version: {version}
Section: graphics
Priority: optional
Architecture: {arch}
Maintainer: SnapMark maintainers <snapmark@localhost>
Installed-Size: {size}
Depends: libglib2.0-bin, libc6 (>= {libc}), libegl1, libgl1, libdbus-1-3, libfontconfig1, libfreetype6, libglib2.0-0t64, libx11-6, libx11-xcb1, libxext6, libxrender1, libxi6, libxkbcommon0, libxkbcommon-x11-0, libxcb1, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render0, libxcb-render-util0, libxcb-shape0, libxcb-shm0, libxcb-sync1, libxcb-xfixes0, libxcb-xinerama0, libxcb-xkb1, libwayland-client0, libwayland-cursor0, libwayland-egl1
Recommends: xdg-desktop-portal, xdg-desktop-portal-gnome
Description: Local screenshot capture and annotation
 Capture screenshots, draw annotations, crop, blur, save and copy images.
 Includes its Python and Qt runtime. Uses the host desktop screenshot portal.
""")
        run("dpkg-deb", "--root-owner-group", "-Zxz", "--build", stage, artifact)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact.with_suffix(".deb.sha256").write_text(f"{digest}  {artifact.name}\n")
    print(artifact)


if __name__ == "__main__":
    main()
