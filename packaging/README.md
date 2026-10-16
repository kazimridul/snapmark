# Ubuntu release packaging

## Bundled Debian installer

Version 0.1.3 is built for **Ubuntu 25.10, amd64**, with glibc 2.42 or newer. The package includes Python, PySide6/Qt, Pillow, D-Bus bindings, and Xlib under `/opt/snapmark`. It installs `/usr/bin/snapmark`, the applications-menu launcher, and the SVG icon. Apt resolves host display libraries. The host supplies the desktop session and screenshot portal.

Install from the repository root:

```bash
sudo apt install ./dist/snapmark_0.1.3_amd64.deb
snapmark
```

Choose SnapMark in the applications menu, or run `snapmark --capture region`. On Wayland v2, Select Window opens the system chooser; choose Window there before taking the screenshot.

Validate the downloaded package in its containing directory:

```bash
sha256sum -c snapmark_0.1.3_amd64.deb.sha256
```

The checksum detects changes; the package is not signed or published to an apt repository. This build is not certified for older Ubuntu versions. PyInstaller bundles depend on the build host's glibc; build and test on the oldest Ubuntu release you want to support.

## Rebuild

On Ubuntu, install dpkg tooling and create a dedicated Python environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]' pyinstaller
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/python tools/build_deb.py
```

The build script creates `dist/snapmark_VERSION_ARCH.deb` and its SHA-256 file. Build dependencies must already be installed; building does not install anything on the host. It uses a temporary staging directory and records Python, OS, and dependency versions under `/usr/share/doc/snapmark/build.json`. Dependency license files are included under `/usr/share/doc/snapmark/third-party`. Python/Qt libraries remain shared files in the installed bundle.

For a Python wheel/source distribution instead, run `.venv/bin/python -m build`. For a source-install desktop launcher, run `.venv/bin/python tools/install_desktop.py`.

## Remove

Disable Launch at login in Settings first, then:

```bash
sudo apt remove snapmark
```

Saved screenshots and user settings/history are preserved. Source-install launchers can be removed separately with `tools/install_desktop.py --uninstall`.

## Verification limits

See [verification](../docs/verification.md). Real screenshot selection, permissions, clipboard sharing, tray, and multiple displays still need the [manual checks](../docs/testing.md). No AppImage is produced by this build.
