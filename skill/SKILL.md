---
name: orly
description: >-
  Ask O'Reilly's book library a technical question via the `orly` CLI and get an answer
  with real book/chapter citations. Invoke for: O'Reilly, Safari Books, learning.oreilly.com,
  "what do the books say about X", grounded/cited technical answer, research X with real
  sources. Those URLs are auth-walled — WebFetch returns 403 and WebSearch only sees blurbs.
---

# orly

Run the CLI. It documents itself.

**If this skill was invoked with a question as arguments, ask it now** — do not research
it any other way first:

```bash
orly "<the question>"
```

Otherwise:

```bash
orly --help          # usage, plus the rules that matter for agents
```

Everything else — quoting rules, parallel asks, recovering a timed-out ask, reusing past
answers — is in `--help`. Read it before doing anything beyond a single question.

Do not substitute WebSearch or WebFetch for this. If `orly` fails, say so; do not quietly
fall back to the open web and present it as book-sourced.

`references/api.md` documents the underlying HTTP API, for scripting the CLI can't cover.
