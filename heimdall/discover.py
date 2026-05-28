"""Discover installed browsers and their profiles on this machine."""
from __future__ import annotations
import os
import json
import configparser
from dataclasses import dataclass

from . import registry
from .registry import Browser


@dataclass
class Profile:
    browser: Browser
    name: str          # friendly name ("Marvz - P", "Default (release)")
    dir_name: str      # on-disk dir/key
    path: str          # absolute path to the profile directory


def installed() -> list[Browser]:
    """Browsers whose data directory exists on this machine."""
    return [b for b in registry.ALL.values() if os.path.isdir(registry.data_dir(b))]


def profiles(b: Browser) -> list[Profile]:
    return _chromium_profiles(b) if b.family == "chromium" else _firefox_profiles(b)


def _chromium_profiles(b: Browser) -> list[Profile]:
    base = registry.data_dir(b)
    names: dict[str, str] = {}
    state = os.path.join(base, "Local State")
    if os.path.isfile(state):
        try:
            with open(state, encoding="utf-8") as fh:
                cache = json.load(fh).get("profile", {}).get("info_cache", {})
            names = {k: v.get("name", k) for k, v in cache.items()}
        except (json.JSONDecodeError, OSError):
            pass
    out = []
    for entry in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        p = os.path.join(base, entry)
        if os.path.isfile(os.path.join(p, "Bookmarks")) or os.path.isfile(os.path.join(p, "History")):
            out.append(Profile(b, names.get(entry, entry), entry, p))
    return out


def _firefox_profiles(b: Browser) -> list[Profile]:
    base = registry.data_dir(b)
    ini = os.path.join(base, "profiles.ini")
    if not os.path.isfile(ini):
        return []
    cp = configparser.ConfigParser()
    cp.read(ini)
    out = []
    for section in cp.sections():
        if not section.startswith("Profile"):
            continue
        rel = cp.get(section, "Path", fallback=None)
        if not rel:
            continue
        is_rel = cp.get(section, "IsRelative", fallback="1") == "1"
        path = os.path.join(base, rel) if is_rel else rel
        name = cp.get(section, "Name", fallback=os.path.basename(rel))
        if os.path.isdir(path):
            out.append(Profile(b, name, rel, path))
    return out
