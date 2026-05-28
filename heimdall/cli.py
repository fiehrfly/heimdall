"""Heimdall CLI: migrate Chromium-family browser data into a Firefox-family browser."""
from __future__ import annotations
import os
import re
import sys
import argparse

from . import discover, migrate, registry
from .discover import Profile
from .adapters import zen
from .passwords import export_csv, PasswordExportError


def _pick(prompt: str, items: list, label) -> object:
    if not items:
        sys.exit(f"Nothing to choose for: {prompt}")
    if len(items) == 1:
        return items[0]
    print(f"\n{prompt}")
    for i, it in enumerate(items, 1):
        print(f"  {i}. {label(it)}")
    while True:
        raw = input("  > ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        print("  (enter a number)")


def _resolve_profile(profs: list[Profile], wanted: str | None, role: str) -> Profile:
    if wanted:
        for p in profs:
            if wanted.lower() in (p.name.lower(), p.dir_name.lower()):
                return p
        sys.exit(f"No {role} profile matching {wanted!r}. Found: {[p.name for p in profs]}")
    return _pick(f"Select {role} profile:", profs, lambda p: f"{p.name}  [{p.dir_name}]")


def _browsers_of(family: str) -> list:
    return [b for b in discover.installed() if b.family == family]


def cmd_list() -> int:
    inst = discover.installed()
    if not inst:
        print("No supported browsers detected on this machine.")
        return 0
    for b in inst:
        kind = "Chromium" if b.family == "chromium" else "Firefox"
        print(f"\n{b.name}  ({kind}, key={b.key})")
        for p in discover.profiles(b):
            extra = ""
            if b.spaces:
                spaces = zen.list_spaces(p.path)
                if spaces:
                    extra = "  spaces: " + ", ".join(s["name"] for s in spaces)
            print(f"    - {p.name}  [{p.dir_name}]{extra}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="heimdall",
        description="Migrate bookmarks/history/passwords from a Chromium-based browser "
                    "to a Firefox-based browser. Defaults to a safe dry-run.",
    )
    ap.add_argument("--list", action="store_true", help="list detected browsers + profiles and exit")
    ap.add_argument("--from", dest="src", metavar="KEY", help="source Chromium browser key (e.g. comet, chrome)")
    ap.add_argument("--from-profile", metavar="NAME", help="source profile name or directory")
    ap.add_argument("--to", dest="dst", metavar="KEY", help="target Firefox browser key (e.g. zen, firefox)")
    ap.add_argument("--to-profile", metavar="NAME", help="target profile name")
    ap.add_argument("--space", metavar="NAME", help="Zen space to file bookmarks under (Zen targets only)")
    ap.add_argument("--folder", metavar="TITLE", help="name of the bookmark folder to create")
    ap.add_argument("--bookmarks", action=argparse.BooleanOptionalAction, default=True, help="migrate bookmarks")
    ap.add_argument("--history", action=argparse.BooleanOptionalAction, default=True, help="migrate history")
    ap.add_argument("--passwords", action=argparse.BooleanOptionalAction, default=False,
                    help="export saved passwords to a Firefox CSV (macOS only)")
    ap.add_argument("--apply", action="store_true", help="write changes (otherwise dry-run)")
    ap.add_argument("--ignore-lock", action="store_true", help="proceed even if the target looks like it's running")
    args = ap.parse_args(argv)

    if args.list:
        return cmd_list()

    src_browser = registry.get(args.src) if args.src else _pick(
        "Select SOURCE (Chromium) browser:", _browsers_of("chromium"), lambda b: b.name)
    dst_browser = registry.get(args.dst) if args.dst else _pick(
        "Select TARGET (Firefox) browser:", _browsers_of("firefox"), lambda b: b.name)
    if src_browser.family != "chromium":
        sys.exit(f"{src_browser.name} is not a Chromium-based source.")
    if dst_browser.family != "firefox":
        sys.exit(f"{dst_browser.name} is not a Firefox-based target.")

    source = _resolve_profile(discover.profiles(src_browser), args.from_profile, "source")
    target = _resolve_profile(discover.profiles(dst_browser), args.to_profile, "target")

    # Resolve a Zen space, if applicable.
    space_uuid = None
    if dst_browser.spaces:
        spaces = zen.list_spaces(target.path)
        if args.space:
            match = [s for s in spaces if s["name"].lower() == args.space.lower()]
            if not match:
                sys.exit(f"No space named {args.space!r}. Found: {[s['name'] for s in spaces]}")
            space_uuid = match[0]["uuid"]
        elif spaces and sys.stdin.isatty():
            choice = _pick("File bookmarks under which space? (or pick 'none')",
                           [{"name": "(none — top-level folder)", "uuid": None}] + spaces,
                           lambda s: s["name"])
            space_uuid = choice["uuid"]

    folder_title = args.folder or f"{src_browser.name} - {source.name}"

    # Safety: don't write into a profile whose browser is open.
    if args.apply and migrate.is_locked(target.path) and not args.ignore_lock:
        sys.exit(f"\n{dst_browser.name} appears to be running (profile lock present).\n"
                 f"Quit it fully, then re-run — or pass --ignore-lock if you're sure.")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\nHeimdall [{mode}]")
    print(f"  source : {src_browser.name} / {source.name}")
    print(f"  target : {dst_browser.name} / {target.name}"
          + (f"  (space: {args.space or 'chosen'})" if space_uuid else ""))
    print(f"  include: bookmarks={args.bookmarks} history={args.history} passwords={args.passwords}")
    print(f"  folder : {folder_title!r}")

    if args.bookmarks or args.history:
        res = migrate.migrate_db(
            source, target,
            do_bookmarks=args.bookmarks, do_history=args.history,
            space_uuid=space_uuid, folder_title=folder_title, apply=args.apply,
        )
        print(f"\n  result : {res.stats}")
        if res.space_bound:
            print(f"  space  : bound {res.space_bound} bookmark(s)/folder(s) to the space")
        for n in res.notes:
            print(f"  note   : {n}")
        if res.backup_dir:
            print(f"  backup : {res.backup_dir}")

    if args.passwords:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{src_browser.key}-{source.name}")
        out = os.path.expanduser(f"~/heimdall-{safe}-passwords.csv")
        if not args.apply:
            print(f"\n  passwords: would export to {out} (run with --apply)")
        else:
            try:
                os.umask(0o077)  # created file is user-only
                n = export_csv(source.path, src_browser, out)
                try:
                    os.chmod(out, 0o600)
                except OSError:
                    pass
                print(f"\n  passwords: exported {n} login(s) -> {out}")
                print(f"  import in {dst_browser.name}: about:logins -> ... -> Import from a File -> select that CSV")
                print(f"  WARNING: {os.path.basename(out)} holds your passwords in PLAINTEXT. "
                      f"Delete it right after importing (it is gitignored, never commit/share it).")
            except PasswordExportError as e:
                print(f"\n  passwords: SKIPPED — {e}")

    if not args.apply:
        print("\n(dry-run; no changes written. Re-run with --apply to migrate.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
