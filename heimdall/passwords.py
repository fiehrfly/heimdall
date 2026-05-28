"""Export Chromium saved passwords to a Firefox-importable CSV.

Firefox/Zen has no command-line password import, so the best a tool can do is
produce the CSV and point the user at `about:logins -> Import from a File`.

Decryption is OS-specific:
  - macOS  : key unwrapped from the login Keychain ("<Browser> Safe Storage"),
             PBKDF2-HMAC-SHA1(1003), AES-128-CBC. IMPLEMENTED.
  - Linux  : key from Secret Service / hardcoded "peanuts" fallback. TODO.
  - Windows: AES-256-GCM key wrapped by DPAPI (and app-bound on v20+). TODO.

Requires the optional `cryptography` dependency (install: `pip install heimdall[passwords]`).
"""
from __future__ import annotations
import os
import sys
import csv
import sqlite3
import hashlib
import subprocess
import tempfile
import shutil

from .registry import Browser


class PasswordExportError(RuntimeError):
    pass


def _require_cryptography():
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # noqa
        return Cipher, algorithms, modes
    except ImportError as e:
        raise PasswordExportError(
            "Password export needs the 'cryptography' package. "
            "Install it with: pip install heimdall[passwords]"
        ) from e


def _macos_key(safe_storage_service: str) -> bytes:
    if not safe_storage_service:
        raise PasswordExportError("This browser has no known Keychain service name.")
    try:
        secret = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", safe_storage_service],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as e:
        raise PasswordExportError(
            f"Could not read '{safe_storage_service}' from the Keychain "
            f"(was access denied?). stderr: {e.stderr.strip()}"
        ) from e
    return hashlib.pbkdf2_hmac("sha1", secret.encode("utf-8"), b"saltysalt", 1003, dklen=16)


def _decrypt_macos(blob: bytes, key: bytes, ciphers) -> str:
    Cipher, algorithms, modes = ciphers
    if blob[:3] not in (b"v10", b"v11"):
        return ""  # unencrypted or unknown scheme; skip
    dec = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    data = dec.update(blob[3:]) + dec.finalize()
    if data:
        data = data[:-data[-1]]  # strip PKCS7 padding
    return data.decode("utf-8", errors="replace")


def export_csv(profile_path: str, browser: Browser, out_path: str) -> int:
    """Write a Firefox-importable CSV of decrypted logins. Returns the row count."""
    if sys.platform != "darwin":
        raise PasswordExportError(
            f"Password export is implemented for macOS only (this is {sys.platform}). "
            "Linux/Windows decryption are not yet supported — export passwords from the "
            "source browser's own password manager and import that CSV into Firefox."
        )
    login_db = os.path.join(profile_path, "Login Data")
    if not os.path.isfile(login_db):
        raise PasswordExportError(f"No 'Login Data' file in {profile_path}")
    ciphers = _require_cryptography()
    key = _macos_key(browser.safe_storage)

    tmp = tempfile.mktemp(suffix=".sqlite")
    shutil.copy(login_db, tmp)
    try:
        con = sqlite3.connect(tmp)
        rows = con.execute("select origin_url, username_value, password_value from logins").fetchall()
        con.close()
    finally:
        os.remove(tmp)

    count = 0
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "url", "username", "password", "note"])
        for origin, username, pw_blob in rows:
            if not origin:
                continue
            password = _decrypt_macos(bytes(pw_blob), key, ciphers) if pw_blob else ""
            host = origin.split("://", 1)[-1].split("/", 1)[0]
            w.writerow([host, origin, username or "", password, ""])
            count += 1
    return count
