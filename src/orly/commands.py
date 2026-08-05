"""One function per subcommand."""

from __future__ import annotations

import json
import sys
import time

from rich.table import Table

from .api import Answers, NotFound
from .auth import (
    AUTH_COOKIES,
    AuthError,
    COOKIE_FILE,
    PASTE_HELP,
    cookies_from_chrome,
    describe_expiry,
    load_cookie,
    save_cookie,
)
from .console import console, err
from .render import emit_json, render

def normalise_question(q: str) -> str:
    """Key for matching a question against one already asked.

    Deliberately shallow: case, surrounding whitespace, and trailing
    punctuation only. "what is a bloom filter" and "What is a bloom filter?"
    are the same question; anything cleverer risks handing back the answer to
    a different one.
    """
    return " ".join((q or "").split()).rstrip("?.!").strip().casefold()


def cmd_ask(args) -> int:
    api = Answers(load_cookie())
    question = " ".join(args.question).strip()

    # `orly ask -` used to ask the literal question "-": a wasted 20s round
    # trip and a junk history entry.
    if question == "-":
        question = sys.stdin.read().strip()

    if not question:
        err.print("[red]error:[/] empty question")
        return 2
    if len(question) < 5:
        err.print(
            f"[red]error:[/] {question!r} is too short to be a question. "
            "Pass it as one argument, or use `-` to read it from stdin."
        )
        return 2

    # An ask is not idempotent: it always creates a new question and costs ~20s.
    # An agent retrying after a timeout therefore duplicates its own work. With
    # --reuse, an identical question already answered is returned instead.
    if args.reuse:
        want = normalise_question(question)
        for row in api.history(args.reuse_scan):
            if normalise_question(row.get("question", "")) == want and row.get(
                "is_finished"
            ):
                qid = row["question_id"]
                err.print(f"reusing answer {qid[:8]} (--reuse); ask again with --no-reuse")
                rec = api.get(qid)
                if rec:
                    if args.json:
                        emit_json(rec, args.raw)
                    else:
                        render(rec, show_sources=not args.no_sources,
                               show_related=args.follow_ups, expand=args.expand)
                    return 0
                break

    qid = api.ask(question)
    # stderr, so a caller piping stdout into a parser is unaffected.
    err.print(f"[dim]question {qid[:8]} created; recover any time with: orly show {qid[:8]}[/]",
              soft_wrap=True)
    if args.json:
        rec = api.wait(qid, timeout=args.timeout)
    else:
        with console.status("[dim]Asking O'Reilly...[/]", spinner="dots") as status:
            rec = api.wait(
                qid,
                timeout=args.timeout,
                on_stage=lambda s: status.update(f"[dim]{s}...[/]"),
            )

    if args.json:
        emit_json(rec, args.raw)
    else:
        render(rec, show_sources=not args.no_sources, show_related=args.follow_ups,
               expand=args.expand)
        console.print()
        console.print(
            f"[dim]saved as[/] [bold]{qid[:8]}[/][dim] - reopen with: orly show {qid[:8]}[/]",
            soft_wrap=True,
        )
        console.print(
            f"[dim]https://learning.oreilly.com/answers2/?questionId={qid}[/]",
            soft_wrap=True,
        )
    return 0


def cmd_history(args) -> int:
    api = Answers(load_cookie())
    rows = api.history(args.number)
    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    table = Table(box=None, pad_edge=False, header_style="bold")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("When", style="dim", no_wrap=True)
    table.add_column("Question")
    table.add_column("ID", style="dim", no_wrap=True)
    for i, r in enumerate(rows, 1):
        table.add_row(
            str(i),
            (r.get("created_time") or "")[:16].replace("T", " "),
            (r.get("question") or "").strip(),
            (r.get("question_id") or "")[:8],
        )
    console.print(table)
    return 0


def cmd_show(args) -> int:
    api = Answers(load_cookie())
    ref = args.id
    if ref.isdigit():  # index into recent history
        rows = api.history(max(int(ref), 20))
        try:
            rec = rows[int(ref) - 1]
        except IndexError:
            raise NotFound(
                f"no history entry #{ref} (only {len(rows)} questions)"
            ) from None
        qid = rec["question_id"]
    else:
        qid = ref
        if len(qid) < 36:  # short prefix from `orly history`
            match = [r for r in api.history(100) if r["question_id"].startswith(qid)]
            if not match:
                raise NotFound(f"no question matching {ref!r} in the last 100")
            qid = match[0]["question_id"]

    rec = api.get(qid)
    if rec is None or not rec.get("is_finished"):
        rec = api.wait(qid, timeout=args.timeout)
    if args.json:
        emit_json(rec, args.raw)
    else:
        render(rec, show_sources=not args.no_sources, show_related=args.follow_ups,
               expand=args.expand)
    return 0


def cmd_auth(args) -> int:
    if args.chrome:
        cookie, profile = cookies_from_chrome(args.profile)
        save_cookie(cookie)
        n = len([p for p in cookie.split("; ") if "=" in p])
        console.print(
            f"[green]OK[/] imported {n} cookies from Chrome "
            f"[dim]({profile})[/] -> {COOKIE_FILE} [dim](0600)[/]"
        )
        args.status = True

    if args.paste:
        # Only print the walkthrough when a human is typing. With a pipe
        # (`echo ... | orly auth --paste`) it is noise.
        if sys.stdin.isatty():
            err.print(PASTE_HELP)
            err.print()
        err.print("Paste the Cookie header, then press Enter:")
        cookie = sys.stdin.readline().strip()
        if not cookie:
            err.print("[red]error:[/] nothing pasted")
            return 2

        names = {p.split("=", 1)[0].strip() for p in cookie.split(";") if "=" in p}
        if missing := [c for c in AUTH_COOKIES if c not in names]:
            err.print(
                f"[red]error:[/] that header is missing {', '.join(missing)}. "
                "Both `orm-jwt` and `orm-rt` are required -- either alone is a 401.\n"
                "Copy the whole Cookie value rather than picking cookies out of it."
            )
            return 2

        save_cookie(cookie)
        console.print(f"[green]OK[/] saved -> {COOKIE_FILE} [dim](0600)[/]")
        args.status = True

    if args.status or not (args.chrome or args.paste):
        try:
            api = Answers(load_cookie())
            rows = api.history(1)
        except AuthError as e:
            err.print(f"[red]not authenticated:[/] {e}")
            return 1
        console.print(
            f"[green]OK[/] signed in; cookie valid "
            f"(probe fetched {len(rows)} past question(s); not a quota)"
        )

        now = time.time()
        for name, exp, source in describe_expiry(load_cookie()):
            if exp is None:
                console.print(f"  [dim]{name}[/]: session cookie (no fixed expiry)")
                continue
            left = exp - now
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(exp))
            if left <= 0:
                console.print(f"  [dim]{name}[/]: [red]expired[/] {when}")
            elif left < 86_400:
                console.print(
                    f"  [dim]{name}[/]: [yellow]{left / 3600:.1f}h[/] left "
                    f"(until {when}) [dim]- {source}[/]"
                )
            else:
                console.print(
                    f"  [dim]{name}[/]: [green]{left / 86_400:.1f} days[/] left "
                    f"(until {when}) [dim]- {source}[/]"
                )
    return 0


# The operating rules live here, not in a skill file, so they cannot drift from
# the behaviour they describe. `--help` is the one thing every caller reads.
