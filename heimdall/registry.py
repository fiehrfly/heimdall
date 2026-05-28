"""Browser registry: where each browser keeps its profile data, per OS.

`family` is either "chromium" or "firefox". Paths are relative to a per-OS root:
  - macOS:   ~/Library/Application Support
  - linux:   ~ (entries include the leading dotdir)
  - windows: %LOCALAPPDATA% for chromium, %APPDATA% for firefox

Coverage note: macOS paths are verified on this machine. Linux/Windows paths
follow each vendor's documented layout but are best-effort until tested.
"""
from __future__ import annotations
import os
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Browser:
    key: str
    name: str
    family: str  # "chromium" | "firefox"
    dirs: dict   # {"darwin": rel, "linux": rel, "win32": rel}
    # chromium-only: macOS Keychain service used to unwrap saved-password key
    safe_storage: str = ""
    # firefox-only: capability flag for Zen-style workspaces ("spaces")
    spaces: bool = False
    aliases: tuple = field(default_factory=tuple)


CHROMIUM = [
    Browser("chrome", "Google Chrome", "chromium",
            {"darwin": "Google/Chrome", "linux": ".config/google-chrome", "win32": r"Google\Chrome\User Data"},
            safe_storage="Chrome Safe Storage"),
    Browser("chromium", "Chromium", "chromium",
            {"darwin": "Chromium", "linux": ".config/chromium", "win32": r"Chromium\User Data"},
            safe_storage="Chromium Safe Storage"),
    Browser("edge", "Microsoft Edge", "chromium",
            {"darwin": "Microsoft Edge", "linux": ".config/microsoft-edge", "win32": r"Microsoft\Edge\User Data"},
            safe_storage="Microsoft Edge Safe Storage"),
    Browser("brave", "Brave", "chromium",
            {"darwin": "BraveSoftware/Brave-Browser", "linux": ".config/BraveSoftware/Brave-Browser", "win32": r"BraveSoftware\Brave-Browser\User Data"},
            safe_storage="Brave Safe Storage"),
    Browser("vivaldi", "Vivaldi", "chromium",
            {"darwin": "Vivaldi", "linux": ".config/vivaldi", "win32": r"Vivaldi\User Data"},
            safe_storage="Vivaldi Safe Storage"),
    Browser("opera", "Opera", "chromium",
            {"darwin": "com.operasoftware.Opera", "linux": ".config/opera", "win32": r"Opera Software\Opera Stable"},
            safe_storage="Opera Safe Storage"),
    Browser("comet", "Comet", "chromium",
            {"darwin": "Comet", "linux": ".config/Comet", "win32": r"Comet\User Data"},
            safe_storage="Comet Safe Storage"),
]

FIREFOX = [
    Browser("firefox", "Firefox", "firefox",
            {"darwin": "Firefox", "linux": ".mozilla/firefox", "win32": r"Mozilla\Firefox"}),
    Browser("zen", "Zen", "firefox",
            {"darwin": "zen", "linux": ".zen", "win32": "zen"}, spaces=True),
    Browser("librewolf", "LibreWolf", "firefox",
            {"darwin": "librewolf", "linux": ".librewolf", "win32": "librewolf"}),
    Browser("waterfox", "Waterfox", "firefox",
            {"darwin": "Waterfox", "linux": ".waterfox", "win32": "Waterfox"}),
    Browser("floorp", "Floorp", "firefox",
            {"darwin": "Floorp", "linux": ".floorp", "win32": "Floorp"}),
    Browser("mullvad", "Mullvad Browser", "firefox",
            {"darwin": "Mullvad Browser", "linux": ".mullvad-browser", "win32": "Mullvad Browser"}),
]

ALL = {b.key: b for b in CHROMIUM + FIREFOX}


def _platform() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform in ("win32", "cygwin"):
        return "win32"
    return sys.platform


def data_dir(b: Browser) -> str:
    """Absolute path to the browser's data directory on this OS (may not exist)."""
    plat = _platform()
    rel = b.dirs.get(plat)
    if rel is None:
        return ""
    if plat == "darwin":
        root = os.path.expanduser("~/Library/Application Support")
    elif plat == "linux":
        root = os.path.expanduser("~")
    elif plat == "win32":
        env = "LOCALAPPDATA" if b.family == "chromium" else "APPDATA"
        root = os.environ.get(env, os.path.expanduser("~"))
    else:
        root = os.path.expanduser("~")
    return os.path.join(root, rel)


def get(key: str) -> Browser:
    return ALL[key]
