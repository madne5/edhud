"""Windows-specific window hardening for the overlay.

Qt gives us ``WindowStaysOnTopHint`` already, but games routinely steal the
z-order back.  These helpers re-assert topmost on a timer and mark the window
as a non-activating tool window so it never appears in Alt+Tab and never
takes focus away from Elite Dangerous.

Every function degrades to a no-op on non-Windows platforms.
"""

from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TRANSPARENT = 0x00000020
WS_EX_APPWINDOW = 0x00040000

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


def _user32():
    if not IS_WINDOWS:
        return None
    try:
        return ctypes.windll.user32
    except Exception:  # pragma: no cover - defensive
        return None


def _get_long(user32, hwnd: int, index: int) -> int:
    if hasattr(user32, "GetWindowLongPtrW"):
        return user32.GetWindowLongPtrW(hwnd, index)
    return user32.GetWindowLongW(hwnd, index)


def _set_long(user32, hwnd: int, index: int, value: int) -> None:
    if hasattr(user32, "SetWindowLongPtrW"):
        user32.SetWindowLongPtrW(hwnd, index, value)
    else:
        user32.SetWindowLongW(hwnd, index, value)


def make_tool_window(hwnd: int, *, click_through: bool) -> bool:
    """Mark the window as non-activating and (optionally) click-through."""
    user32 = _user32()
    if user32 is None or not hwnd:
        return False
    try:
        style = _get_long(user32, hwnd, GWL_EXSTYLE)
        style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        style &= ~WS_EX_APPWINDOW
        if click_through:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        _set_long(user32, hwnd, GWL_EXSTYLE, style)
        return True
    except Exception as exc:  # pragma: no cover - platform specific
        log.debug("cannot set extended window style: %s", exc)
        return False


def assert_topmost(hwnd: int) -> bool:
    """Push the window back to the top of the z-order without focusing it."""
    user32 = _user32()
    if user32 is None or not hwnd:
        return False
    try:
        return bool(
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        )
    except Exception as exc:  # pragma: no cover - platform specific
        log.debug("SetWindowPos failed: %s", exc)
        return False


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def foreground_is_fullscreen(hwnd: int) -> bool:
    """True when the foreground window covers a whole monitor.

    Exclusive-fullscreen games cannot be overlaid at all, so this is only used
    to print a one-time hint telling the player to switch to borderless.
    """
    user32 = _user32()
    if user32 is None:
        return False
    try:
        fg = user32.GetForegroundWindow()
        if not fg or fg == hwnd:
            return False
        rect = RECT()
        if not user32.GetWindowRect(fg, ctypes.byref(rect)):
            return False
        monitor = user32.MonitorFromWindow(fg, 2)  # MONITOR_DEFAULTTONEAREST
        if not monitor:
            return False
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        mon = info.rcMonitor
        return (
            rect.left <= mon.left
            and rect.top <= mon.top
            and rect.right >= mon.right
            and rect.bottom >= mon.bottom
        )
    except Exception:
        return False
