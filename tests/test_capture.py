import asyncio
import threading
from types import SimpleNamespace
import pytest
from dbus_next import Message, MessageType, Variant
from cpp.capture.backend import Capabilities, CaptureCancelled, capture, capabilities, portal_capture, session_type
from cpp.storage import save_image


class FakeBus:
    unique_name = ":1.42"
    def __init__(self, uri, code=0):
        self.handler = None
        self.uri = uri
        self.code = code
        self.options = {}
        self.disconnected = False
        self.closed = False

    async def connect(self):
        return self

    def add_message_handler(self, handler):
        self.handler = handler

    def remove_message_handler(self, handler):
        self.handler = None

    def disconnect(self):
        self.disconnected = True

    async def call(self, message):
        if message.member == "Screenshot":
            self.options = message.body[1]
            token = self.options["handle_token"].value
            path = f"/org/freedesktop/portal/desktop/request/1_42/{token}"
            # Deliberately send before method return to catch the portal response race.
            if self.code is not None:
                self.handler(Message.new_signal(path, "org.freedesktop.portal.Request", "Response", "ua{sv}",
                    [self.code, {"uri": Variant("s", self.uri)}]))
            return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=[path])
        if message.member == "Close":
            self.closed = True
        return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=[])


@pytest.mark.parametrize("mode,version,targets,target", [
    ("full", 2, 0, None), ("region", 2, 0, None), ("window", 2, 0, None), ("full", 3, 15, 1),
    ("region", 3, 15, 4), ("window", 3, 15, 8), ("window", 3, 3, 2),
])
def test_portal_options_response_race_and_cleanup(app, image, tmp_path, monkeypatch, mode, version, targets, target):
    path = tmp_path / "capture with spaces.png"
    save_image(image, path)
    bus = FakeBus(path.as_uri())
    monkeypatch.setattr("dbus_next.aio.MessageBus", lambda: bus)
    caps = Capabilities("wayland", True, True, True, "test", version, targets)
    result = asyncio.run(portal_capture(mode, caps, threading.Event()))
    assert result.size() == image.size()
    assert bus.disconnected and bus.handler is None
    assert bus.options["interactive"].value == (mode != "full")
    assert (bus.options["target"].value if "target" in bus.options else None) == target


def test_portal_denial_cancel_and_invalid_uri(monkeypatch):
    caps = Capabilities("wayland", True, True, False, "test", 2)
    for code, uri, error in [(1, "file:///tmp/no.png", CaptureCancelled),
                             (2, "file:///tmp/no.png", RuntimeError),
                             (0, "https://example.com/image.png", RuntimeError)]:
        bus = FakeBus(uri, code)
        monkeypatch.setattr("dbus_next.aio.MessageBus", lambda: bus)
        with pytest.raises(error):
            asyncio.run(portal_capture("full", caps, threading.Event()))
        assert bus.disconnected
    bus = FakeBus("", None)
    monkeypatch.setattr("dbus_next.aio.MessageBus", lambda: bus)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(CaptureCancelled):
        asyncio.run(portal_capture("full", caps, cancelled))
    assert bus.closed and bus.disconnected


def test_environment_detection_and_no_silent_fallback(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":0")
    assert session_type() == "wayland"
    def broken():
        raise OSError("portal not installed")
    monkeypatch.setattr("cpp.capture.backend.portal_capabilities", broken)
    caps = capabilities()
    assert not caps.full and caps.session == "wayland"
    assert "portal not installed" in caps.description
    with pytest.raises(RuntimeError):
        capture("full", caps, threading.Event())
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert session_type() == "x11"
    monkeypatch.delenv("DISPLAY", raising=False)
    assert session_type() == "none"


def test_x11_native_pixel_capture_without_desktop(app, monkeypatch):
    from PIL import Image
    calls = []
    def grab(**kwargs):
        calls.append(kwargs)
        return Image.new("RGB", (400, 200), "red")
    monkeypatch.setattr("PIL.ImageGrab.grab", grab)
    caps = Capabilities("x11", True, True, False, "test")
    result = capture("full", caps, threading.Event())
    assert result.size().toTuple() == (400, 200)
    assert result.devicePixelRatio() == 1
    assert result.pixelColor(10, 10).red() == 255
    assert calls[0]["bbox"] is None


def test_portal_capability_query_avoids_unrelated_introspection(monkeypatch):
    from cpp.capture.backend import portal_capabilities
    class CapabilityBus(FakeBus):
        async def call(self, message):
            assert message.interface == "org.freedesktop.DBus.Properties"
            assert message.member == "GetAll"
            assert message.body == ["org.freedesktop.portal.Screenshot"]
            return SimpleNamespace(message_type=MessageType.METHOD_RETURN,
                body=[{"version": Variant("u", 3), "AvailableTargets": Variant("u", 5)}])
    bus = CapabilityBus("")
    monkeypatch.setattr("dbus_next.aio.MessageBus", lambda: bus)
    caps = asyncio.run(portal_capabilities())
    assert caps.full and caps.region and not caps.window
    assert caps.portal_version == 3 and caps.targets == 5
    assert bus.disconnected


@pytest.mark.parametrize("session,version,targets,expected", [
    ("wayland", 1, 0, True), ("wayland", 2, 0, False),
    ("wayland", 3, 5, False), ("wayland", 3, 1, True), ("x11", 0, 0, True),
])
def test_region_selector_is_owned_by_one_backend(session, version, targets, expected):
    from cpp.capture.backend import needs_local_region_selection
    caps = Capabilities(session, True, True, False, "test", version, targets)
    assert needs_local_region_selection(caps) is expected


def test_portal_screen_fallback_does_not_launch_native_region_selector(app, image, tmp_path, monkeypatch):
    path = tmp_path / "full.png"
    save_image(image, path)
    bus = FakeBus(path.as_uri())
    monkeypatch.setattr("dbus_next.aio.MessageBus", lambda: bus)
    caps = Capabilities("wayland", True, True, False, "test", 3, 1)
    asyncio.run(portal_capture("region", caps, threading.Event()))
    assert bus.options["target"].value == 1
    assert bus.options["interactive"].value is False


@pytest.mark.parametrize("version,targets,available", [(1, 0, False), (2, 0, True),
    (3, 1, False), (3, 2, True), (3, 8, True)])
def test_window_capabilities_include_legacy_interactive_chooser(monkeypatch, version, targets, available):
    from cpp.capture.backend import portal_capabilities
    class CapabilityBus(FakeBus):
        async def call(self, message):
            return SimpleNamespace(message_type=MessageType.METHOD_RETURN,
                body=[{"version": Variant("u", version), "AvailableTargets": Variant("u", targets)}])
    bus = CapabilityBus("")
    monkeypatch.setattr("dbus_next.aio.MessageBus", lambda: bus)
    caps = asyncio.run(portal_capabilities())
    assert caps.window is available
    assert bus.disconnected
