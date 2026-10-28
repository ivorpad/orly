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
uv tool install 'git+https://github.com/ivorpad/orly.git@v0.2.1'
```

For development, install from a local checkout:

```bash
uv tool install --editable .
```

You need your own O'Reilly subscription; this is a client, not a way around one. The
session is cached at `~/.config/orly/cookie` (mode 0600) and never leaves the machine.

### Authenticating

**macOS + Chrome**, on a Mac where reading browser cookies is allowed:

```bash
orly auth --chrome              # type yes, then one Keychain prompt; --profile "Profile 2" to pick one
```

Before touching anything, `--chrome` says what it will read (Chrome's `Cookies` database
and the `Chrome Safe Storage` Keychain item) and waits for you to type `yes`. Any other
answer, or no terminal at all (an agent, a pipe, CI), stops it before it lists Chrome's
profile folder, and no flag skips the question. On a Mac whose policy forbids reading
browser cookies, such as a corporate laptop, never type yes there and use `--paste`.

**Anything else**: paste the header once.

```bash
pbpaste | orly auth --paste     # Linux: wl-paste or xclip -o -selection clipboard
```

Sign in at learning.oreilly.com, open DevTools → Network, click any request to that
domain, and copy the whole `Cookie:` request header. `orm-jwt` and `orm-rt` are the two
that matter — either alone is a 401, so copy the lot rather than picking them out. A
paste missing one is rejected before it is saved.

Pipe it in. `orly auth --paste` on its own prints the walkthrough and reads the header at
a hidden prompt, but macOS drops a pasted line longer than 1023 bytes, Enter included,
so with a full header that prompt just waits. A piped header never appears on screen
either, so the session stays out of your scrollback.

To move a session to another Mac, run `pbcopy < ~/.config/orly/cookie` on the one where
orly is signed in, get that text onto the other Mac's clipboard, and run
`pbpaste | orly auth --paste` there. The paste is checked for both auth cookies, saved
with mode 0600 and probed against the API, so `OK signed in` means that Mac is ready
without its browser ever being read.

For scripts, CI, and containers, set `ORLY_COOKIE` to the same string; it takes priority
over the cached file.

`orly auth --status` checks the saved session with the API and prints the access
token's expiry. The refresh token's expiry is unavailable from the saved cookie.
Only `orly auth --chrome` reads Chrome's cookie database or accesses the Keychain, and
only after you type yes.

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

The coding harness's model selects examples and writes the playbook. The CLI
fetches evidence and extracts code locally; it does not call another model.

Search the requested subject across different books using narrow questions.
Read relevant passages and code from multiple books before writing the playbook;
do not assume the first book or chapter covers the subject. Prefer examples for
the requested library version. Merge duplicate rules, keep version differences
explicit, and report missing evidence or unresolved conflicts. Respect rate
limits and `Retry-After`, reuse answers, and fetch each selected chapter once.

```bash
orly read 'https://learning.oreilly.com/library/view/-/9781492056348/ch18.html' --raw --json > chapter.json
orly extract chapter.json                       # compact index of all code blocks
orly extract chapter.json --block b44            # full example and nearby explanation
orly extract chapter.json --block b44 --json     # structured evidence
```

Save the chapter outside a public repository. After the initial fetch, these
`extract` calls require no network or authentication. `extract -` accepts a
payload on stdin. The default output is Markdown; `--json` has a versioned schema.
Book citations are hidden by default (`--source false`); use `--source true` to
include book titles, chapter URLs, and source links in Markdown or JSON.
Use the index's `chapter_sha256` with `--snapshot SHA256` to reject block IDs
from a different snapshot. Unknown IDs are an error; unrecognized code markup
returns an explicit evidence gap. Previews are bounded; selected code is whole.

Examples retain original fragment links, labels when present, source hashes,
and nearby explanations. Callout markers are separated from code, and
nonbreaking spaces become ordinary spaces; these mechanical changes are
reported. The original text remains available in the saved HTML and `read`
output. A reference may identify a section rather than an individual listing.

Select relevant examples from the index instead of assuming code after a
citation applies. Write concise Markdown rules and correct code examples taken
from the evidence. Omit feedback/feedforward sections, proposed tests, and book
citations by default. Use actual book code in the requested language; do not
adapt, translate, modernize, or invent examples. Only reported mechanical
cleanup is allowed. Preserve chapter dependencies and explain missing setup.
Verify generated Answers claims against chapter passages and listings; a citation
alone does not establish a claim. Report gaps instead of filling them with code
or advice from memory. Retain original code references internally even when
citations are hidden from the playbook.

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
practice you sign in again (`auth --paste`, or `auth --chrome` where it's allowed) only
after a month idle, or if O'Reilly invalidates the session.

## Layout

```
src/orly/
  cli.py         argparse, dispatch, and the agent notes printed by --help
  commands.py    one function per subcommand
  api.py         the Answers HTTP client
  chapter.py     chapter HTML extraction and block selection
  evidence.py    local code index and excerpts for the harness model
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
