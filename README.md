# Heimdall

Migrate your **bookmarks, history, and saved passwords** from any **Chromium-based**
browser to any **Firefox-based** browser.

Heimdall exists because there's no native tool for this. Chromium browsers
(Chrome, Edge, Brave, Vivaldi, Opera, **Comet**, …) and Firefox browsers
(Firefox, **Zen**, LibreWolf, Waterfox, Floorp, …) use different engines and
on-disk formats, so the usual "import from another browser" wizards don't cover
cross-engine moves like Comet → Zen.

It's deterministic and fully offline — no accounts, no network calls, no LLM.

## What it migrates

| Data | How | Notes |
|------|-----|-------|
| **Bookmarks** | Rebuilt directly in the target's `places.sqlite`, folder tree preserved | On Zen, can be filed under a named **space** |
| **History** | Direct write with Chrome→Firefox timestamp + visit-type conversion | URLs de-duplicated against existing history |
| **Passwords** | Decrypted from the source and exported to a Firefox-importable CSV | **macOS only** for now; Firefox has no CLI import, so you finish in `about:logins` |

What can **not** cross the engine boundary: cookies/sessions (you'll re-log in —
the passwords cover that) and extensions (Chromium and Firefox use different
add-on stores). Heimdall doesn't pretend otherwise.

## Prerequisites

**All platforms**

- **Python 3.9 or newer** and `pip`
- Both browsers installed locally with the profiles you want to migrate (the
  source Chromium profile and the target Firefox profile)
- Quit the **target** browser before running with `--apply`

**macOS — Apple Silicon *and* Intel (identical requirements)**

- Python 3.9+ — the preinstalled `python3`, or from [python.org](https://www.python.org/downloads/macos/) or Homebrew (`brew install python`)
- For the `--passwords` toggle: `pip install '.[passwords]'`. This pulls
  [`cryptography`](https://pypi.org/project/cryptography/), which ships prebuilt
  wheels for **both arm64 and x86_64** — so **no Rosetta, Xcode, or Rust toolchain
  is needed on Intel**. On first run you'll get a one-time macOS Keychain prompt to
  read the browser's "Safe Storage" key.
- Nothing about Intel vs Apple Silicon changes the steps.

**Linux**

- Python 3.9+ and `pip` (e.g. `sudo apt install python3 python3-pip`)
- Bookmarks + history are fully supported.
- **Passwords: not yet supported.** Export them from the source browser's own
  password manager and import that CSV into Firefox via `about:logins`.

**Windows**

- Python 3.9+ from [python.org](https://www.python.org/downloads/windows/) (tick
  *"Add python.exe to PATH"* during install)
- Bookmarks + history are supported.
- **Passwords: not yet supported** (Windows DPAPI decryption is TODO) — use the
  source browser's own export.

## Install

```bash
pip install -e .                # core (bookmarks + history)
pip install -e '.[passwords]'   # adds 'cryptography' for the passwords toggle (macOS)
```

## Usage

```bash
# See what Heimdall detects on this machine
heimdall --list

# Safe dry-run (default): interactively pick source + target, write nothing
heimdall

# Non-interactive, explicit, and actually apply
heimdall --from comet --from-profile "Marvz - P" \
         --to zen --to-profile "Default (release)" \
         --space "P" --apply
```

### Toggles

Everything is opt-out except passwords (opt-in):

```bash
heimdall --no-history          # bookmarks only
heimdall --no-bookmarks        # history only
heimdall --passwords --apply   # also export the passwords CSV
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--bookmarks` / `--no-bookmarks` | on | migrate bookmarks |
| `--history` / `--no-history` | on | migrate history |
| `--passwords` / `--no-passwords` | off | export passwords to CSV (macOS) |
| `--space NAME` | — | Zen target: file bookmarks under this space |
| `--folder TITLE` | `"<Source> - <profile>"` | bookmark folder name |
| `--apply` | off (dry-run) | actually write changes |
| `--ignore-lock` | off | proceed even if the target browser looks open |

## Safety

- **Dry-run by default.** Nothing is written until you pass `--apply`.
- Every apply first copies the target `places.sqlite` (+ `-wal`/`-shm`) to a
  timestamped `~/heimdall-backup-YYYYMMDD-HHMMSS/`.
- Writes run inside a transaction gated by `PRAGMA integrity_check` and
  `PRAGMA foreign_key_check` — any failure rolls back.
- Heimdall refuses to write into a profile whose browser is still running
  (it checks the Firefox profile lock). **Quit the target browser first.**
- The source profile is only ever opened read-only.
- The exported passwords CSV contains **plaintext** credentials. Heimdall writes
  it `0600` (user-only), gitignores it, and reminds you to delete it after import.
  Never commit or share it. Heimdall never prints password values to the console.

## Platform support

macOS is verified. Linux and Windows paths follow each vendor's documented
layout and should work, but are best-effort until tested; password decryption is
macOS-only so far (Linux Secret Service and Windows DPAPI are TODO).

## How the bookmarks/history write works

Firefox stores everything in `places.sqlite`. Heimdall reproduces the exact
on-disk formats — origins, `rev_host`, and the 64-bit `url_hash` (reverse-engineered
and validated against a real profile: 514/516 rows reproduced exactly) — then lets
Firefox recompute frecency on next launch via the `recalc_*` flags. See
`heimdall/places_hash.py` and `heimdall/firefox.py`.

## License

MIT — see [LICENSE](LICENSE).
