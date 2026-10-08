"""Run a PowerShell snippet in a real visible console window and screenshot that window."""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


def find_window(title: str) -> int:
    for _ in range(60):
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            return hwnd
        time.sleep(0.5)
    raise SystemExit(f"window not found: {title}")


def frame_bounds(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def capture(name: str, snippet: Path, width: int, height: int, wait: int) -> None:
    title = f"FabricOps-{name}"
    done = Path(f"artifacts/{name}.done").resolve()
    done.unlink(missing_ok=True)
    snippet_path = snippet.resolve()
    script = (
        f"$Host.UI.RawUI.WindowTitle='{title}'; "
        "function prompt { 'PS> ' }; "
        "$cfg='config\\examples\\synthetic-healthcare\\project.yml'; Clear-Host; "
        f"$s=Get-Content -Raw '{snippet_path}'; Write-Host ('PS> ' + $s.Trim()); Write-Host ''; "
        f"Invoke-Expression $s; New-Item -Force '{done}' | Out-Null"
    )
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-NoExit", "-Command", script],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    hwnd = find_window(title)
    user32.MoveWindow(hwnd, 60, 40, width, height, True)
    for _ in range(wait):
        if done.exists():
            break
        time.sleep(1)
    time.sleep(2)
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(1)
    left, top, right, bottom = frame_bounds(hwnd)
    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    Path("docs/images").mkdir(parents=True, exist_ok=True)
    image.save(f"docs/images/{name}.png")
    proc.terminate()
    user32.PostMessageW(hwnd, 0x0010, 0, 0)


if __name__ == "__main__":
    capture(sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]))
