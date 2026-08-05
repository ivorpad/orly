# orly

A command line client for [O'Reilly Answers](https://learning.oreilly.com/answers2/) —
ask a technical question, get an answer with the books and chapters it came from.

Built by recording what the web app does and deriving a direct client, so it skips the
browser entirely.

```
$ orly "why do connection pools need a maximum size?"

why do connection pools need a maximum size?

A connection pool's maximum size exists because each physical database
connection consumes finite server-side resources [1][2] ...

Sources
 1. High Performance MySQL, 4th Edition (2021)
    Connection Pooling
    Silvia Botros, Jeremy Tinley
    https://learning.oreilly.com/library/view/-/9781492080503/ch04.html
 ...
```

## Install

Needs [`uv`](https://docs.astral.sh/uv/).

```bash
uv tool install --editable .
orly auth --chrome        # imports your signed-in session from Chrome
```

`auth --chrome` decrypts Chrome's cookie store, which means one Keychain prompt. The
session is cached at `~/.config/orly/cookie` (mode 0600) and never leaves the machine.
You need your own O'Reilly subscription; this is a client, not a way around one.

## Use

```bash
orly "when should you use event sourcing?"   # ask; `ask` is the default verb
orly "..." --expand                          # + the verbatim passage from each source
orly "..." --json                            # answer + citations, machine-readable
orly history                                 # past questions (shared with the website)
orly show 3 --expand                         # re-read one by index, id, or id prefix
orly auth --status                           # session expiry
orly --help                                  # everything, including the agent notes
```

Each ask takes ~20s. There is no streaming — the API returns nothing until the answer is
complete — so run independent questions at once:

```bash
orly "q1" > a.txt & orly "q2" > b.txt & wait
```

## Using it from an agent

`skill/` is a Claude Code skill. Symlink it in and an agent can invoke the CLI directly
instead of scraping the web for book quotes it never actually read:

```bash
ln -s "$PWD/skill" ~/.claude/skills/orly
```

The skill body deliberately does almost nothing — it tells the agent to run `orly`, and
`orly --help` carries the operating rules. Keeping them in `--help` means they cannot
drift from the behaviour they describe.

Be aware that skill auto-triggering is unreliable: prompts that name O'Reilly tend to fire
it, prompts that just say "what do the books say" often do not. Invoke it explicitly when
it matters.

## Auth, in more detail

Two cookies do the work: `orm-jwt` (access JWT, ~1h) and `orm-rt` (refresh token). Either
alone is a 401; together the gateway refreshes silently. `groot_sessionid`, despite
looking like the session, is not used by this API at all.

The server re-issues both cookies on every response, so `orly` writes the jar back
atomically after each call and the session rolls 30 days forward from last use. In
practice you re-run `auth --chrome` only after a month idle, or if O'Reilly invalidates
the session.

## Layout

```
src/orly/
  cli.py         argparse, dispatch, and the agent notes printed by --help
  commands.py    one function per subcommand
  api.py         the Answers HTTP client
  auth.py        Chrome cookie extraction and session persistence
  render.py      terminal output and the JSON shapes
  console.py     the two shared rich consoles
tests/
```

This started as one 847-line file. The split follows the seams that were already there —
auth, transport, presentation, dispatch — rather than a layer diagram imposed on top.
Sub-commands stay in a single `commands.py`; four functions totalling ~150 lines do not
need a package of their own, and the cost of splitting further is more import plumbing
than it saves in navigation.

What was given up: the old single file carried its dependencies inline (PEP 723) and ran
straight from `uv run`, so it could be copied anywhere and just work. That is a real loss.
It is paid for with a test suite, a proper entry point, and modules you can read in one
sitting.

## Caveats

This talks to a private, undocumented API that can change without notice. The retrieval
filter (`FQ` in the script) encodes your account's entitlements as captured at build time;
if your subscription changes it will go stale and should be re-captured.

`skill/references/api.md` documents the endpoints, the polling behaviour, and the cookie
scheme.
