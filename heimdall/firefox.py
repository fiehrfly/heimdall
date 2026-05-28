"""Write migrated data into a Firefox-family `places.sqlite`.

This is the deterministic core. Every insert mirrors the formats observed in a
live profile: origins (prefix='scheme://', plain host), places (rev_host, verified
url_hash, recalc flags so Firefox recomputes frecency), bookmarks (12-char GUIDs),
and history visits (Unix-microsecond visit_date, mapped visit_type).
"""
from __future__ import annotations
import sqlite3
import secrets

from .places_hash import url_hash, rev_host
from .chromium import HistoryUrl, Visit, BookmarkNode

TOOLBAR_PARENT = 3  # moz_bookmarks 'toolbar_____'
GUID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

# Chromium core transition type -> Firefox visit_type.
_TRANSITION = {0: 1, 1: 2, 2: 3, 3: 5, 5: 6, 6: 4}


def split_url(url: str):
    """(scheme, host) for http/https URLs, else (None, None)."""
    if "://" not in url:
        return None, None
    scheme, rest = url.split("://", 1)
    if scheme not in ("http", "https"):
        return None, None
    host = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.split("@")[-1].split(":")[0]
    return (scheme, host) if host else (None, None)


def _new_guid(con) -> str:
    while True:
        g = "".join(secrets.choice(GUID_ALPHABET) for _ in range(12))
        if not con.execute("select 1 from moz_places where guid=?", (g,)).fetchone() \
           and not con.execute("select 1 from moz_bookmarks where guid=?", (g,)).fetchone():
            return g


def _origin_id(con, scheme, host) -> int:
    prefix = scheme + "://"
    row = con.execute("select id from moz_origins where prefix=? and host=?", (prefix, host)).fetchone()
    if row:
        return row[0]
    con.execute(
        "insert into moz_origins(prefix,host,frecency,recalc_frecency,recalc_alt_frecency) values(?,?,1,1,1)",
        (prefix, host),
    )
    return con.execute("select last_insert_rowid()").fetchone()[0]


def _place_id(con, url, title, last_visit_us) -> int | None:
    scheme, host = split_url(url)
    if scheme is None:
        return None
    row = con.execute("select id,last_visit_date from moz_places where url=?", (url,)).fetchone()
    if row:
        pid, lvd = row
        new_lvd = max(lvd or 0, last_visit_us or 0) or None
        con.execute(
            "update moz_places set last_visit_date=?, frecency=-1, recalc_frecency=1, recalc_alt_frecency=1 where id=?",
            (new_lvd, pid),
        )
        return pid
    oid = _origin_id(con, scheme, host)
    con.execute(
        """insert into moz_places(url,title,rev_host,visit_count,hidden,typed,frecency,
             last_visit_date,guid,foreign_count,url_hash,origin_id,recalc_frecency,recalc_alt_frecency)
           values(?,?,?,0,0,0,-1,?,?,0,?,?,1,1)""",
        (url, title, rev_host(host), last_visit_us or None, _new_guid(con), url_hash(url), oid),
    )
    return con.execute("select last_insert_rowid()").fetchone()[0]


def import_history(con, urls: dict[int, HistoryUrl], visits: list[Visit]) -> dict:
    stats = {"urls": 0, "visits": 0, "skipped": 0}
    chrome_to_place: dict[int, int] = {}
    for cid, u in urls.items():
        pid = _place_id(con, u.url, u.title, u.last_visit_us)
        if pid is None:
            stats["skipped"] += 1
            continue
        chrome_to_place[cid] = pid
        stats["urls"] += 1
    for v in visits:
        pid = chrome_to_place.get(v.url_id)
        if pid is None:
            continue
        con.execute(
            "insert into moz_historyvisits(from_visit,place_id,visit_date,visit_type,session,source) values(0,?,?,?,0,0)",
            (pid, v.visit_us, _TRANSITION.get(v.transition_core, 1)),
        )
        stats["visits"] += 1
    # Rebuild visit_count / last_visit_date from what was actually inserted.
    con.execute(
        """update moz_places set
             visit_count=(select count(*) from moz_historyvisits v where v.place_id=moz_places.id),
             last_visit_date=(select max(visit_date) from moz_historyvisits v where v.place_id=moz_places.id)
           where id in (select distinct place_id from moz_historyvisits)"""
    )
    return stats


def import_bookmarks(con, root: BookmarkNode, folder_title: str, ts_us: int) -> tuple[list[str], dict]:
    """Recreate the bookmark tree under a new toolbar folder. Returns (created_guids, stats)."""
    stats = {"bookmarks": 0, "folders": 0, "skipped": 0}
    created: list[str] = []

    pos = (con.execute("select max(position) from moz_bookmarks where parent=?", (TOOLBAR_PARENT,)).fetchone()[0] or -1) + 1
    root_guid = _new_guid(con)
    con.execute(
        """insert into moz_bookmarks(type,fk,parent,position,title,dateAdded,lastModified,guid,syncStatus,syncChangeCounter)
           values(2,NULL,?,?,?,?,?,?,1,1)""",
        (TOOLBAR_PARENT, pos, folder_title, ts_us, ts_us, root_guid),
    )
    root_id = con.execute("select last_insert_rowid()").fetchone()[0]
    created.append(root_guid)

    def insert_children(node: BookmarkNode, parent_id: int):
        for i, child in enumerate(node.children):
            guid = _new_guid(con)
            if child.is_folder:
                con.execute(
                    """insert into moz_bookmarks(type,fk,parent,position,title,dateAdded,lastModified,guid,syncStatus,syncChangeCounter)
                       values(2,NULL,?,?,?,?,?,?,1,1)""",
                    (parent_id, i, child.title, ts_us, ts_us, guid),
                )
                fid = con.execute("select last_insert_rowid()").fetchone()[0]
                created.append(guid)
                stats["folders"] += 1
                insert_children(child, fid)
            else:
                pid = _place_id(con, child.url, child.title, None)
                if pid is None:
                    stats["skipped"] += 1
                    continue
                con.execute(
                    """insert into moz_bookmarks(type,fk,parent,position,title,dateAdded,lastModified,guid,syncStatus,syncChangeCounter)
                       values(1,?,?,?,?,?,?,?,1,1)""",
                    (pid, parent_id, i, child.title, ts_us, ts_us, guid),
                )
                con.execute("update moz_places set foreign_count=foreign_count+1 where id=?", (pid,))
                created.append(guid)
                stats["bookmarks"] += 1

    # Flatten the synthetic top-level roots (bookmark_bar/other/...) directly under our folder.
    flat = BookmarkNode(title="")
    for top in root.children:
        flat.children.extend(top.children if top.is_folder else [top])
    insert_children(flat, root_id)
    return created, stats


def integrity_ok(con) -> tuple[bool, str]:
    ic = con.execute("PRAGMA integrity_check").fetchone()[0]
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    if ic != "ok" or fk:
        return False, f"integrity_check={ic} foreign_key_violations={fk}"
    return True, "ok"
