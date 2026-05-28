"""Read source data out of a Chromium profile (read-only, never modified)."""
from __future__ import annotations
import os
import json
import sqlite3
from dataclasses import dataclass, field

# Microseconds between 1601-01-01 (Chromium/WebKit epoch) and 1970-01-01 (Unix/PRTime epoch).
CHROME_EPOCH_OFFSET_US = 11644473600000000


@dataclass
class BookmarkNode:
    title: str
    url: str | None = None              # None => folder
    children: list = field(default_factory=list)

    @property
    def is_folder(self) -> bool:
        return self.url is None


@dataclass
class HistoryUrl:
    url: str
    title: str | None
    last_visit_us: int | None          # already converted to Unix microseconds


@dataclass
class Visit:
    url_id: int
    visit_us: int                      # Unix microseconds
    transition_core: int               # Chromium core transition type (transition & 0xFF)


def read_bookmarks(profile_path: str) -> BookmarkNode:
    """Return a synthetic root folder mirroring the Chromium bookmark tree."""
    path = os.path.join(profile_path, "Bookmarks")
    root = BookmarkNode(title="")
    if not os.path.isfile(path):
        return root
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    def build(node) -> list[BookmarkNode]:
        out = []
        for ch in node.get("children", []):
            if ch.get("type") == "url":
                out.append(BookmarkNode(title=ch.get("name", ch["url"]), url=ch["url"]))
            elif ch.get("type") == "folder":
                folder = BookmarkNode(title=ch.get("name", "Folder"))
                folder.children = build(ch)
                out.append(folder)
        return out

    for key, val in data.get("roots", {}).items():
        if isinstance(val, dict) and val.get("children"):
            sub = BookmarkNode(title=val.get("name", key))
            sub.children = build(val)
            root.children.append(sub)
    return root


def read_history(profile_path: str) -> tuple[dict[int, HistoryUrl], list[Visit]]:
    """Return ({chrome_url_id: HistoryUrl}, [Visit]). Opens History read-only/immutable."""
    path = os.path.join(profile_path, "History")
    if not os.path.isfile(path):
        return {}, []
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        urls = {}
        for cid, url, title, last in con.execute(
                "select id,url,title,last_visit_time from urls"):
            last_us = (last - CHROME_EPOCH_OFFSET_US) if last else None
            urls[cid] = HistoryUrl(url=url, title=title or None, last_visit_us=last_us)
        visits = [
            Visit(url_id=uid, visit_us=vt - CHROME_EPOCH_OFFSET_US, transition_core=(tr or 0) & 0xFF)
            for uid, vt, tr in con.execute("select url, visit_time, transition from visits")
            if vt
        ]
        return urls, visits
    finally:
        con.close()
