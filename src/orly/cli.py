"""Argument parsing and dispatch.

AGENT_NOTES lives here rather than in a skill file so the operating rules
cannot drift from the behaviour they describe: --help is the one thing every
caller reads.
"""

from __future__ import annotations

import argparse
import sys

import httpx

from .auth import AuthError
from .commands import cmd_ask, cmd_auth, cmd_history, cmd_show
from .console import err

AGENT_NOTES = """\
answers come from O'Reilly's book library, with the book and chapter cited.

  orly "when should you use event sourcing?"     ask; `ask` is the default verb
  orly "..." --expand                            + the verbatim passage per source
  orly "..." --json                              answer + citations, machine-readable
  orly history                                   past questions (shared with the website)
  orly show <id|index> [--expand]                re-read one; free and instant

if you are an agent, this part matters:

  * Use this, not WebSearch. learning.oreilly.com is auth-walled: WebFetch gets
    403 and search only sees blurbs. This reads the real text.
  * Answer only from what comes back. Do not top it up with other docs or your
    own knowledge, and never call those "aligned with O'Reilly guidance".
  * A quote marked "[... truncated mid-sentence]" is cut. Quote it short or drop
    it. Do not write the missing words.
  * Ask narrow questions, not compound ones. "Postgres vs DynamoDB for SaaS" is
    three questions; retrieval is better on each one separately.
  * Each ask costs ~20s, so run independent ones at once:
        orly "q1" >a.txt & orly "q2" >b.txt & wait
  * Nothing is lost. The id is printed as soon as the question exists. If a wait
    times out, `orly show <id>` — never re-ask, that duplicates and costs 20s.
  * Check `orly history` before asking; the answer may already be there.
"""


def main() -> int:
    p = argparse.ArgumentParser(
        prog="orly",
        description="Ask O'Reilly Answers from the terminal.",
        epilog=AGENT_NOTES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd")

    def common(sp):
        sp.add_argument("--json", action="store_true",
                        help="machine-readable answer + citations (~1k tokens)")
        sp.add_argument("--raw", action="store_true",
                        help="with --json: the untouched API record, chapter HTML "
                             "and all (~14k tokens; you rarely want this)")
        sp.add_argument("--no-sources", action="store_true", help="hide the source list")
        sp.add_argument("--follow-ups", action="store_true", help="show related questions")
        sp.add_argument(
            "--expand",
            "--quotes",
            dest="expand",
            action="store_true",
            help="print the verbatim passage cited from each source",
        )
        sp.add_argument(
            "--timeout",
            type=float,
            default=180.0,
            metavar="SEC",
            help="seconds to wait for the answer (default: 180)",
        )

    a = sub.add_parser("ask", help="ask a question")
    a.add_argument("question", nargs="+")
    common(a)
    a.set_defaults(func=cmd_ask)

    h = sub.add_parser("history", help="list previous questions")
    h.add_argument("-n", "--number", type=int, default=20)
    h.add_argument("--json", action="store_true")
    h.set_defaults(func=cmd_history)

    s = sub.add_parser("show", help="re-display a previous answer")
    s.add_argument("id", help="question id, id prefix, or history index")
    common(s)
    s.set_defaults(func=cmd_show)

    au = sub.add_parser("auth", help="manage the session cookie")
    au.add_argument("--chrome", action="store_true", help="import cookies from Chrome")
    au.add_argument("--profile", metavar="NAME", help="Chrome profile, e.g. 'Profile 2'")
    au.add_argument("--paste", action="store_true", help="read a Cookie header from stdin")
    au.add_argument("--status", action="store_true", help="check the saved cookie works")
    au.set_defaults(func=cmd_auth)

    # `orly "some question"` is shorthand for `orly ask ...`
    argv = sys.argv[1:]
    if argv and argv[0] not in {"ask", "history", "show", "auth", "-h", "--help"}:
        argv = ["ask", *argv]
    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 0

    try:
        return args.func(args)
    except AuthError as e:
        err.print(f"[red]auth error:[/] {e}")
        return 1
    except (httpx.HTTPError, RuntimeError, TimeoutError) as e:
        err.print(f"[red]error:[/] {e}")
        return 1
    except KeyboardInterrupt:
        return 130


