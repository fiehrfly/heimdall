"""Zen-browser target adapter: bind migrated bookmarks to a Zen 'space' (workspace).

Zen stores space membership in the `zen_bookmarks_workspaces` table inside
places.sqlite (bookmark_guid -> workspace_uuid). Space *names* live in the
session store `zen-sessions.jsonlz4` (Mozilla LZ4 framed JSON). Other Firefox
forks have no such table, so callers must check `has_spaces()` first.
"""
from __future__ import annotations
import os
import json
import struct


def has_spaces(con) -> bool:
    return bool(con.execute(
        "select 1 from sqlite_master where type='table' and name='zen_bookmarks_workspaces'"
    ).fetchone())


def _lz4_block_decompress(src: bytes, out_size: int) -> bytes:
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]; i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1; lit += b
                if b != 255:
                    break
        out += src[i:i + lit]; i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8); i += 2
        mlen = (token & 0xF) + 4
        if (token & 0xF) == 15:
            while True:
                b = src[i]; i += 1; mlen += b
                if b != 255:
                    break
        start = len(out) - off
        for j in range(mlen):
            out.append(out[start + j])
    return bytes(out)


def _read_mozlz4(path: str) -> bytes | None:
    with open(path, "rb") as f:
        if f.read(8)[:6] != b"mozLz4":
            return None
        size = struct.unpack("<I", f.read(4))[0]
        return _lz4_block_decompress(f.read(), size)


def list_spaces(profile_path: str) -> list[dict]:
    """Return [{'uuid','name','icon'}] for the profile, or [] if none found."""
    path = os.path.join(profile_path, "zen-sessions.jsonlz4")
    if not os.path.isfile(path):
        return []
    try:
        raw = _read_mozlz4(path)
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except (OSError, ValueError):
        return []
    out = []
    for s in data.get("spaces", []):
        if isinstance(s, dict) and "uuid" in s and "name" in s:
            out.append({"uuid": s["uuid"], "name": s["name"], "icon": s.get("icon", "")})
    return out


def bind_to_space(con, guids: list[str], space_uuid: str, ts_ms: int) -> int:
    for g in guids:
        con.execute(
            "insert into zen_bookmarks_workspaces(bookmark_guid,workspace_uuid,created_at,updated_at) values(?,?,?,?)",
            (g, space_uuid, ts_ms, ts_ms),
        )
    return len(guids)
