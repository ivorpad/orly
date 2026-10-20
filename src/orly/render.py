"""Turning an answer record into terminal output or JSON."""

from __future__ import annotations

import html as html_mod
import json
import re
import sys

from rich.markdown import Markdown

from .console import console, err

CITE = re.compile(r"\[\[\^(\d+)\]\]\([^)]*\)")


def clean_quote(text: str) -> str:
    """The cited passage as plain prose.

    `highlight_text` arrives with hard line breaks where the book or transcript
    wrapped, which is noise in a quotation. `snippet` is the same passage with
    <mark> around it, and is the fallback when the plain field is absent.
    """
    text = re.sub(r"</?mark>", "", text or "")
    text = html_mod.unescape(text)
    return " ".join(text.split())


def flag_truncation(quote: str) -> str:
    """Make a chopped passage obviously chopped.

    O'Reilly cuts the highlight at a character budget, not a sentence boundary,
    so a passage can stop mid-word. Rendered bare, that reads as a complete
    quotation and a caller will tidy up the ending -- one agent handed this
    output silently "completed" `...backup jobs at specifi` to
    `at specifi[c intervals]` and presented it as a direct quote. An explicit
    marker is the difference between a short quote and a fabricated one.
    """
    q = (quote or "").rstrip()
    if not q:
        return q
    if q[-1] in ".!?" or q[-1] in "\"')]" or q.endswith("..."):
        return q
    return q + " [... truncated mid-sentence; do not complete it]"


def render(rec: dict, show_sources: bool = True, show_related: bool = False,
           expand: bool = False) -> None:
    data = (rec.get("miso_response") or {}).get("data") or {}
    answer = data.get("answer") or ""
    if not answer:
        err.print("[yellow]No answer text in the response.[/]")
        return

    console.print()
    console.print(f"[bold]{rec.get('question', '').strip()}[/]")
    console.print()
    console.print(Markdown(CITE.sub(r"[\1]", answer)))

    sources = data.get("sources") or []
    if show_sources and sources:
        console.print()
        console.print("[bold]Sources[/]")
        for i, s in enumerate(sources, 1):
            title = s.get("title") or "(untitled)"
            chapter = s.get("child_title")
            who = ", ".join(s.get("authors") or [])
            year = (s.get("date") or "")[:4]
            head = f"[cyan]{i:>2}.[/] [bold]{title}[/]"
            if year:
                head += f" [dim]({year})[/]"
            console.print(head)
            if chapter:
                console.print(f"    [italic]{chapter}[/]")
            if who:
                console.print(f"    [dim]{who}[/]")
            # soft_wrap keeps the URL on one logical line so it stays clickable
            console.print(
                f"    [blue]{s.get('child_url') or s.get('url') or ''}[/]",
                soft_wrap=True,
            )

            # The passage O'Reilly actually cited, verbatim. This is the whole
            # reason to prefer Answers over a web search: it is a quotable line
            # from a named book with a link to the exact spot. It arrives in
            # every response and used to be dropped on the floor here, which
            # left a caller with a list of titles and nothing to quote.
            if expand:
                quote = flag_truncation(
                    clean_quote(s.get("highlight_text") or s.get("snippet") or "")
                )
                if quote:
                    console.print()
                    console.print(f'    [italic]"{quote}"[/]', soft_wrap=True)
                pub = ", ".join((s.get("custom_attributes") or {}).get("publishers") or [])
                if pub:
                    console.print(f"    [dim]{pub}[/]")
                console.print()

        # Say the flag exists, in the output, where a caller will actually meet
        # it. An agent handed `orly ask ...` sees the answer and a list of
        # links; nothing tells it the verbatim quotes are one flag away, so it
        # does not ask for them. A man page nobody reads cannot fix that.
        if not expand:
            qid = (data.get("question_id") or "")[:8]
            quotable = sum(
                1 for s in sources if (s.get("highlight_text") or s.get("snippet"))
            )
            if quotable:
                console.print()
                console.print(
                    f"[dim]{quotable} of these carry the verbatim passage O'Reilly cited. "
                    f"To get them: [/][bold]orly show {qid} --expand[/]"
                    f"[dim]  (or --json for everything)[/]"
                )

    # Both keys exist in the response and only one is ever filled: the API
    # puts the questions in `followup_questions` and leaves
    # `related_questions` an empty list. Reading only the latter made
    # --follow-ups a flag that printed nothing, silently, always.
    related = (data.get("followup_questions") or data.get("related_questions") or [])
    if show_related and related:
        console.print()
        console.print("[bold]Follow-ups[/]")
        for q in related:
            console.print(f"  [dim]-[/] {q if isinstance(q, str) else q.get('question', q)}")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def compact(rec: dict) -> dict:
    """The answer and its citations, without the payload that blows up a caller.

    The raw record includes book catalog HTML blurbs, not chapter markup,
    plus a verbatim echo of the request config. Keep what a citation needs.
    Fetch actual chapter HTML with `orly read`.
    """
    data = (rec.get("miso_response") or {}).get("data") or {}
    return {
        "question_id": rec.get("question_id"),
        "question": rec.get("question"),
        "asked_at": rec.get("created_time"),
        "answer": CITE.sub(r"[\1]", data.get("answer") or ""),
        "sources": [
            {
                "n": i,
                "title": s.get("title"),
                "chapter": s.get("child_title"),
                "authors": s.get("authors") or [],
                "year": (s.get("date") or "")[:4] or None,
                "url": s.get("child_url") or s.get("url"),
                "quote": flag_truncation(
                    clean_quote(s.get("highlight_text") or s.get("snippet") or "")
                )
                or None,
            }
            for i, s in enumerate(data.get("sources") or [], 1)
        ],
        "follow_ups": data.get("followup_questions") or data.get("related_questions") or [],
    }


def emit_json(rec: dict, raw: bool) -> None:
    json.dump(rec if raw else compact(rec), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


