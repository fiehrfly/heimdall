"""Orchestration: backups, lock safety, dry-run vs apply, integrity gate."""
from __future__ import annotations
import os
import time
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field

from . import firefox, chromium
from .adapters import zen
from .discover import Profile

# Firefox writes one of these into a profile while running.
_LOCK_FILES = ("lock", ".parentlock", "parent.lock")


@dataclass
class Result:
    applied: bool
    working_db: str
    backup_dir: str | None = None
    stats: dict = field(default_factory=dict)
    space_bound: int = 0
    notes: list = field(default_factory=list)


def is_locked(profile_path: str) -> bool:
    return any(os.path.lexists(os.path.join(profile_path, f)) for f in _LOCK_FILES)


def backup(places_path: str) -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.expanduser(f"~/heimdall-backup-{ts}")
    os.makedirs(dest, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        p = places_path + suffix
        if os.path.exists(p):
            shutil.copy2(p, dest)
    return dest


def migrate_db(source: Profile, target: Profile, *, do_bookmarks: bool, do_history: bool,
               space_uuid: str | None, folder_title: str, apply: bool) -> Result:
    places = os.path.join(target.path, "places.sqlite")
    if not os.path.isfile(places):
        raise FileNotFoundError(f"target has no places.sqlite: {places}")

    backup_dir = None
    if apply:
        backup_dir = backup(places)
        working = places
    else:
        working = tempfile.mktemp(suffix=".sqlite")
        shutil.copy2(places, working)

    res = Result(applied=apply, working_db=working, backup_dir=backup_dir)
    con = sqlite3.connect(working)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        if do_history:
            urls, visits = chromium.read_history(source.path)
            res.stats["history"] = firefox.import_history(con, urls, visits)
        if do_bookmarks:
            root = chromium.read_bookmarks(source.path)
            ts_us = int(time.time() * 1_000_000)
            guids, bstats = firefox.import_bookmarks(con, root, folder_title, ts_us)
            res.stats["bookmarks"] = bstats
            if space_uuid:
                if zen.has_spaces(con):
                    res.space_bound = zen.bind_to_space(con, guids, space_uuid, int(time.time() * 1000))
                else:
                    res.notes.append("target has no Zen-style spaces; bookmarks placed in a folder only")

        ok, detail = firefox.integrity_ok(con)
        if not ok:
            con.rollback()
            raise RuntimeError(f"integrity check failed, rolled back: {detail}")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    if not apply:
        # dry-run worked on a throwaway copy; leave it for inspection then drop
        try:
            os.remove(working)
        except OSError:
            pass
    return res
