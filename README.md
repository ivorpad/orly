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
uv tool install 'git+https://github.com/ivorpad/orly.git@v0.2.0'
```

For development, install from a local checkout:

```bash
uv tool install --editable .
```

You need your own O'Reilly subscription; this is a client, not a way around one. The
session is cached at `~/.config/orly/cookie` (mode 0600) and never leaves the machine.

### Authenticating

**macOS + Chrome** — automatic:

```bash
orly auth --chrome              # one Keychain prompt; --profile "Profile 2" to pick one
```

**Anything else** — paste the header once:

```bash
orly auth --paste               # prints the DevTools walkthrough, then reads stdin
```

Sign in at learning.oreilly.com, open DevTools → Network, click any request to that
domain, and copy the whole `Cookie:` request header. `orm-jwt` and `orm-rt` are the two
that matter — either alone is a 401, so copy the lot rather than picking them out. A
paste missing one is rejected before it is saved. Nothing appears on screen as you paste;
the input is hidden so the session does not end up in your scrollback.

For scripts, CI, and containers, set `ORLY_COOKIE` to the same string; it takes priority
over the cached file.

`orly auth --status` checks the session and prints both expiries.

> `--chrome` is macOS-only. It reads Chrome's cookie DB via the Keychain, and Linux
> (gnome-keyring/kwallet) and Windows (DPAPI) encrypt those cookies differently. Rather
> than ship crypto I cannot test, those platforms use `--paste`, which works everywhere
> and with any browser.

## Use

```bash
orly "when should you use event sourcing?"   # ask; `ask` is the default verb
orly "..." --expand                          # + the verbatim passage from each source
orly "..." --json                            # answer + citations, machine-readable
orly history                                 # past questions (shared with the website)
orly show 3 --expand                         # re-read one by index, id, or id prefix
orly read 42daa7c4 1                         # prose and code from source 1's chapter
orly read 42daa7c4 1 --code --from-citation --limit 1
orly read https://learning.oreilly.com/library/view/-/9781098100650/ch14.html
orly auth --status                           # session expiry
orly --help                                  # everything, including the agent notes
```

`read` fetches one chapter using your existing session. It prints prose, code,
and numbered explanations, with book references and links to other chapters or
examples. `--code` keeps examples, captions, and their numbered explanations.
`--from-citation` starts where the cited passage ends; `--start 'some text'`
works for either an answer source or a URL. Matching ignores whitespace; citation
matching can use a unique suffix when the search excerpt's formatting differs.

The default limit is 12 whole blocks. Use `--limit N` to adjust it. A code block
is never cut in half and can be large. `--json` returns structured blocks,
references, and a `remaining_blocks` count; `--raw` prints the entire chapter
HTML, or the full chapter payload with `--json`. Selection flags cannot be
combined with `--raw`. This reads one file per call, without crawling the book.

For the code immediately after a citation:

```bash
orly read 42daa7c4 1 --code --from-citation --limit 1  # Fluent Python, Example 15-5
orly read 72a52ac5 5 --code --from-citation --limit 1  # Robust Python, load_restaurant
```

Answer records only contain the cited passage, usually at most 1,200 characters.
Their `sources[].html` is the book's catalog blurb, including under `show --json
--raw`; it does not contain the chapter. Use `read` for the book text.

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
  chapter.py     chapter HTML extraction and block selection
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

This talks to a private, undocumented API that can change without notice.

The retrieval filter ships as content-type and language only (`DEFAULT_FQ` in `api.py`).
The real one the web app sends also carries a list of permission exclusions, which spell
out precisely what a subscription is entitled to, so that is not in here. The cost is that
search can surface a result your account cannot open. To pin it to your own entitlements,
copy the `fq` from the POST your browser makes to `/questions/` and set `ORLY_FQ` to it.

`skill/references/api.md` documents the endpoints, the polling behaviour, and the cookie
scheme.
