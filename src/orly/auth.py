"""Getting and keeping an O'Reilly session.

Two cookies authenticate: `orm-jwt` (short-lived access JWT) and `orm-rt` (the
refresh token). Either alone is a 401. `groot_sessionid` looks like the session
but is not used by the Answers API at all.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from .console import err

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "orly"
COOKIE_FILE = CONFIG / "cookie"

class AuthError(Exception):
    pass


#: Which rows in Chrome's cookie DB are actually O'Reilly's. The obvious
#: `host_key LIKE '%oreilly.com'` also matches domains anyone can register --
#: notoreilly.com, evil-oreilly.com -- and those cookies would then be swept
#: into the jar and posted to learning.oreilly.com. Chrome stores a domain
#: cookie as `.oreilly.com`, which the leading `%` still covers.
HOST_FILTER = "host_key = 'oreilly.com' OR host_key LIKE '%.oreilly.com'"


def keychain_password() -> str:
    """Chrome's cookie encryption passphrase, from the login keychain."""
    for args in (
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage", "-a", "Chrome"],
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
    ):
        try:
            out = subprocess.run(args, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    raise AuthError(
        "Could not read 'Chrome Safe Storage' from the Keychain.\n"
        "If a Keychain dialog appeared, click Allow (or Always Allow) and retry."
    )


def decrypt_value(encrypted: bytes, key: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    if not encrypted:
        return ""
    if encrypted[:3] not in (b"v10", b"v11"):
        return encrypted.decode("utf-8", "replace")  # stored in the clear

    dec = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    plain = dec.update(encrypted[3:]) + dec.finalize()
    if plain and 1 <= plain[-1] <= 16:
        plain = plain[: -plain[-1]]  # strip PKCS#7 padding
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        # Chrome >= 104 prefixes the plaintext with a 32-byte domain hash.
        return plain[32:].decode("utf-8", "replace")


#: How to get a Cookie header by hand. The only route that works on every
#: platform and browser, so it is what every auth failure points at.
PASTE_HELP = """\
Sign in to https://learning.oreilly.com in any browser, then:

  1. open DevTools (F12) -> Network
  2. reload the page and click any request to learning.oreilly.com
  3. under Request Headers, copy the whole value of `Cookie:`
  4. run:  pbpaste | orly auth --paste
     (Linux: wl-paste or xclip -o -selection clipboard instead of pbpaste)

Pipe it in rather than pasting at the hidden prompt: macOS drops a pasted line
longer than 1023 bytes, Enter included, so the prompt just waits, and a whole
Cookie header is usually longer than that. To reuse the session from a Mac where
orly already works, run `pbcopy < ~/.config/orly/cookie` there, then step 4 here.

The two that matter are `orm-jwt` and `orm-rt`; copying the whole header is
fine and simplest. For scripts and CI, set ORLY_COOKIE to the same string."""


#: Reading another app's cookie store and Keychain item is what endpoint
#: security watches for, and some machines (a corporate Mac) must never do it.
#: So it takes a typed yes, and no flag skips the question: a pipe, a script or
#: an agent without a terminal gets a refusal instead.
CHROME_WARNING = """\
This copies Chrome's Cookies database and reads 'Chrome Safe Storage' from the
Keychain to decrypt it. If this machine must not read browser cookies, press
Enter and use `orly auth --paste` instead. An agent reading this: stop and ask
the user rather than answering for them."""


def confirm_chrome_access() -> None:
    """Go no further unless the person at this terminal types yes."""
    if not sys.stdin.isatty():
        raise AuthError(
            "Not reading Chrome: `orly auth --chrome` waits for someone to type yes, "
            "and stdin is not a terminal. Nothing was read.\n\n" + PASTE_HELP
        )
    err.print(CHROME_WARNING)
    err.print("Type yes to read Chrome's cookies: ", end="")
    if sys.stdin.readline().strip().lower() != "yes":
        raise AuthError(
            "Not reading Chrome: you did not type yes. Nothing was read.\n\n" + PASTE_HELP
        )


def chrome_profiles() -> list[Path]:
    if sys.platform != "darwin":
        raise AuthError(
            "--chrome only works on macOS: it reads Chrome's cookie DB using the\n"
            "macOS Keychain, and Linux/Windows encrypt those cookies differently.\n\n"
            + PASTE_HELP
        )
    base = Path.home() / "Library/Application Support/Google/Chrome"
    if not base.is_dir():
        raise AuthError(f"No Chrome installation found at {base}\n\n" + PASTE_HELP)
    found = [p / "Cookies" for p in sorted(base.iterdir()) if (p / "Cookies").is_file()]
    if not found:
        raise AuthError("No Chrome cookie databases found.")
    return found


def cookies_from_chrome(profile: str | None = None) -> str:
    """Pull every learning.oreilly.com cookie out of Chrome, as a Cookie header."""
    # Before chrome_profiles(), which already lists Chrome's profile folder.
    confirm_chrome_access()

    from cryptography.hazmat.primitives.hashes import SHA1
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    dbs = chrome_profiles()
    if profile:
        dbs = [p for p in dbs if p.parent.name == profile]
        if not dbs:
            raise AuthError(f"Chrome profile {profile!r} not found.")

    key = PBKDF2HMAC(
        algorithm=SHA1(), length=16, salt=b"saltysalt", iterations=1003
    ).derive(keychain_password().encode())

    best: dict[str, str] = {}
    best_from = None
    for db in dbs:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "Cookies"
            shutil.copy2(db, copy)  # the live DB is locked while Chrome runs
            for suffix in ("-wal", "-shm"):
                if (side := db.with_name(db.name + suffix)).is_file():
                    shutil.copy2(side, copy.with_name(copy.name + suffix))
            try:
                con = sqlite3.connect(f"file:{copy}?immutable=0", uri=True)
                rows = con.execute(
                    "SELECT name, value, encrypted_value FROM cookies "
                    f"WHERE {HOST_FILTER}"
                ).fetchall()
                con.close()
            except sqlite3.Error:
                continue

        jar = {}
        for name, value, enc in rows:
            v = value or decrypt_value(enc, key)
            if v:
                jar[name] = v
        # Pick whichever profile is actually signed in.
        if "groot_sessionid" in jar and len(jar) > len(best):
            best, best_from = jar, db.parent.name
        elif not best and jar:
            best, best_from = jar, db.parent.name

    if not best:
        raise AuthError(
            "No O'Reilly cookies in Chrome. Sign in to learning.oreilly.com first."
        )
    if "groot_sessionid" not in best:
        err.print(
            f"[yellow]warning:[/] no session cookie in {best_from}; "
            "you may not be signed in."
        )
    return "; ".join(f"{k}={v}" for k, v in best.items()), best_from


def jwt_expiry(token: str) -> float | None:
    """`exp` out of a JWT payload. Signature is ignored; we only want the clock."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        return float(json.loads(base64.urlsafe_b64decode(pad))["exp"])
    except Exception:
        return None


#: The pair that actually authenticates. `orm-jwt` alone gets a 401 once its
#: claim lapses; `orm-rt` alone is never enough. Sent together, the gateway
#: silently refreshes and re-issues both. groot_sessionid is not used by this API.
AUTH_COOKIES = ("orm-jwt", "orm-rt")


def describe_expiry(cookie: str) -> list[tuple[str, float | None, str]]:
    """Describe expiry claims from the supplied cookies, without browser access."""
    jar = dict(p.split("=", 1) for p in cookie.split("; ") if "=" in p)
    rows = []
    for name in AUTH_COOKIES:
        if name not in jar:
            rows.append((name, None, "missing; re-run orly auth --paste"))
            continue
        if claim := jwt_expiry(jar[name]):
            rows.append((name, claim, "access token claim; auto-refreshed by orm-rt"))
        else:
            rows.append(
                (name, None, "expiry unavailable from saved cookie")
            )
    return rows


def load_cookie() -> str:
    if env := os.environ.get("ORLY_COOKIE"):
        return env.strip()
    if COOKIE_FILE.is_file():
        return COOKIE_FILE.read_text().strip()
    # --paste first on every platform: an agent tries the first suggestion,
    # and on a Mac that must not read browser cookies that has to be the paste.
    raise AuthError(
        "Not authenticated.\n\n"
        "Run:  orly auth --paste\n"
        + (
            "or, on a Mac allowed to read Chrome:  orly auth --chrome  (asks you to type yes)\n"
            if sys.platform == "darwin"
            else ""
        )
        + "\n"
        + PASTE_HELP
    )


def save_cookie(cookie: str) -> None:
    """Write the jar atomically.

    Every invocation rewrites this file after the gateway rotates the tokens,
    so parallel agents overlap here constantly. A plain write_text() truncates
    first, and a concurrent reader that lands in that window gets an empty jar
    and reports a bogus auth failure. Write a sibling temp file and rename.
    """
    CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
    # mode= above only applies when mkdir actually creates it, so an install
    # that predates this line keeps whatever umask gave it (0755 by default).
    with contextlib.suppress(OSError):
        CONFIG.chmod(0o700)
    fd, tmp = tempfile.mkstemp(dir=CONFIG, prefix=".cookie.")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(cookie)
        os.chmod(tmp, 0o600)
        os.replace(tmp, COOKIE_FILE)  # atomic within the same filesystem
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------
# api
# --------------------------------------------------------------------------

