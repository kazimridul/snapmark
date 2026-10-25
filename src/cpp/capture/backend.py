"""Desktop capture, without framebuffer access on Wayland."""
import asyncio
from dataclasses import dataclass
import os
import threading
from urllib.parse import unquote, urlparse
import uuid
from PySide6.QtGui import QImage
from cpp.storage import read_image


class CaptureCancelled(Exception):
    pass


@dataclass(frozen=True)
class Capabilities:
    session: str
    full: bool
    region: bool
    window: bool
    description: str
    portal_version: int = 0
    targets: int = 0


def needs_local_region_selection(caps: Capabilities) -> bool:
    """The v2 interactive portal already returns the user's selected area."""
    if caps.session != "wayland":
        return True
    if caps.portal_version < 2:
        return True
    return caps.portal_version >= 3 and not caps.targets & 4


def session_type() -> str:
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    return "x11" if os.environ.get("DISPLAY") else "none"


async def portal_capabilities() -> Capabilities:
    from dbus_next import Message, MessageType
    from dbus_next.aio import MessageBus
    bus = await MessageBus().connect()
    try:
        # Do not introspect the entire portal object: unrelated GNOME interfaces
        # can contain property names that dbus-next's XML parser rejects.
        reply = await asyncio.wait_for(bus.call(Message(destination="org.freedesktop.portal.Desktop",
            path="/org/freedesktop/portal/desktop", interface="org.freedesktop.DBus.Properties",
            member="GetAll", signature="s", body=["org.freedesktop.portal.Screenshot"])), 5)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError("; ".join(str(value) for value in reply.body))
        values = reply.body[0]
        version = values.get("version").value if "version" in values else 1
        targets = values.get("AvailableTargets").value if "AvailableTargets" in values else 0
        full = version < 3 or bool(targets & 1)
        # A returned screenshot can always be cropped locally for a region.
        # v2 has an interactive desktop chooser, but cannot preselect a
        # window target. Let the user choose Window there (e.g. GNOME).
        window = version == 2 or (version >= 3 and bool(targets & (2 | 8)))
        description = "Wayland · desktop screenshot portal"
        if version == 2:
            description += ". For a window screenshot, choose Window in the system screenshot chooser."
        if not window:
            description += ". Window capture is unavailable on this portal; use Region instead."
        return Capabilities("wayland", full, full or bool(targets & 4), window, description, version, targets)
    finally:
        bus.disconnect()


def capabilities() -> Capabilities:
    session = session_type()
    if session == "wayland":
        try:
            return asyncio.run(portal_capabilities())
        except Exception as exc:
            return Capabilities(session, False, False, False,
                "Screenshot portal unavailable. Check xdg-desktop-portal and your GNOME portal backend. " + str(exc))
    if session == "x11":
        try:
            from PIL import features
            from Xlib.display import Display
            display = Display()
            atoms = display.screen().root.get_full_property(display.intern_atom("_NET_SUPPORTED"), 0)
            active = display.intern_atom("_NET_ACTIVE_WINDOW")
            window = atoms is not None and active in atoms.value
            display.close()
            if not features.check_feature("xcb"):
                raise RuntimeError("Pillow was built without XCB screenshot support.")
            return Capabilities(session, True, True, window, "X11 · full desktop in native pixels. Region selection follows capture.")
        except Exception as exc:
            return Capabilities(session, False, False, False, "X11 capture unavailable: " + str(exc))
    return Capabilities(session, False, False, False, "No desktop display detected. You can still open and edit image files.")


async def portal_capture(mode: str, caps: Capabilities, cancelled: threading.Event) -> QImage:
    from dbus_next import Message, MessageType, Variant
    from dbus_next.aio import MessageBus
    bus = await MessageBus().connect()
    token = "snapmark_" + uuid.uuid4().hex
    sender = bus.unique_name.lstrip(":").replace(".", "_")
    request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    future = asyncio.get_running_loop().create_future()
    def response(message):
        if message.message_type == MessageType.SIGNAL and message.interface == "org.freedesktop.portal.Request" and message.member == "Response" and message.path == request_path:
            if not future.done():
                future.set_result(message.body)
    bus.add_message_handler(response)
    try:
        reply = await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus", member="AddMatch", signature="s",
            body=["type='signal',interface='org.freedesktop.portal.Request',member='Response'"]))
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError("Cannot subscribe to screenshot portal responses.")
        # A non-interactive full-screen request can be denied before a consent UI
        # is shown. Always use the desktop's user-authorized flow (v2+).
        interactive = caps.portal_version >= 2
        options = {"handle_token": Variant("s", token), "interactive": Variant("b", interactive)}
        if caps.portal_version >= 3:
            target = 1 if mode == "full" else 4 if mode == "region" and caps.targets & 4 else 1
            if mode == "window":
                target = 8 if caps.targets & 8 else 2
            options["target"] = Variant("u", target)
        reply = await asyncio.wait_for(bus.call(Message(destination="org.freedesktop.portal.Desktop",
            path="/org/freedesktop/portal/desktop", interface="org.freedesktop.portal.Screenshot",
            member="Screenshot", signature="sa{sv}", body=["", options])), 15)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError("Screenshot portal: " + "; ".join(str(x) for x in reply.body))
        request_path = reply.body[0]
        deadline = asyncio.get_running_loop().time() + 180
        while not future.done():
            if cancelled.is_set() or asyncio.get_running_loop().time() > deadline:
                await bus.call(Message(destination="org.freedesktop.portal.Desktop", path=request_path,
                                       interface="org.freedesktop.portal.Request", member="Close"))
                raise CaptureCancelled("Capture cancelled.")
            await asyncio.sleep(.1)
        code, result = future.result()
        if code == 1:
            raise CaptureCancelled("Capture cancelled in the system dialog.")
        if code != 0 or "uri" not in result:
            raise RuntimeError("The desktop did not authorize or complete the screenshot. Approve the system capture dialog and select Screen for a full screenshot. If permission was denied previously, check your desktop screenshot permissions.")
        uri = urlparse(result["uri"].value)
        if uri.scheme != "file" or uri.netloc not in ("", "localhost"):
            raise RuntimeError("The portal returned an unsupported image location.")
        return read_image(unquote(uri.path))
    finally:
        bus.remove_message_handler(response)
        bus.disconnect()


def x11_capture(mode: str) -> QImage:
    from PIL import ImageGrab
    box = None
    if mode == "window":
        from Xlib.display import Display
        display = Display()
        try:
            root = display.screen().root
            prop = root.get_full_property(display.intern_atom("_NET_ACTIVE_WINDOW"), 0)
            if prop is None or not len(prop.value) or not prop.value[0]:
                raise RuntimeError("The window manager did not report an active window. Use Region instead.")
            window = display.create_resource_object("window", int(prop.value[0]))
            geometry = window.get_geometry()
            # translate_coords maps from source into the destination root.
            position = root.translate_coords(window, 0, 0)
            box = (position.x, position.y, position.x + geometry.width, position.y + geometry.height)
        finally:
            display.close()
    image = ImageGrab.grab(bbox=box, xdisplay=os.environ.get("DISPLAY")).convert("RGBA")
    data = image.tobytes()
    return QImage(data, image.width, image.height, image.width*4, QImage.Format.Format_RGBA8888).copy()


def capture(mode: str, caps: Capabilities, cancelled: threading.Event) -> QImage:
    if mode not in ("full", "region", "window") or not getattr(caps, mode):
        raise RuntimeError("This capture mode is unavailable. " + caps.description)
    if cancelled.is_set():
        raise CaptureCancelled("Capture cancelled.")
    if caps.session == "wayland":
        return asyncio.run(portal_capture(mode, caps, cancelled))
    return x11_capture(mode)
