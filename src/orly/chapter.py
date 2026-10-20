"""Extract readable blocks from one chapter, preserving code whitespace."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .api import NotFound


def normalise(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def blocks(html: str, url: str = "") -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav"]):
        tag.decompose()
    root = soup.body or soup
    for image in root.select("a.co img[alt]"):
        image.replace_with(image["alt"])

    def links(tag):
        return [{"text": " ".join(a.get_text().split()), "url": urljoin(url, a["href"])}
                for a in tag.find_all("a", href=True)
                if "co" not in a.get("class", [])
                and urljoin(url, a["href"]).startswith(("https://", "http://"))]

    def prose(tag):
        return " ".join(tag.get_text().split())

    out = []
    for tag in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "pre", "li", "caption", "figcaption"]):
        if tag.find_parent(["pre", "p", "figcaption", "caption", "h1", "h2", "h3", "h4", "h5", "h6"]):
            continue
        if tag.name == "li" and tag.find(["p", "pre"]):
            continue
        code = tag.name == "pre"
        text = tag.get_text("", strip=False)
        text = text.strip("\n") if code else " ".join(text.split())
        if not text.strip():
            continue
        block = {"kind": "code" if code else "text", "text": text}
        if refs := links(tag):
            block["references"] = refs
        if not code and tag.find_parent("dd"):
            dt = tag.find_parent("dd").find_previous_sibling("dt")
            if dt:
                block["text"] = prose(dt) + ". " + text
        if code:
            # EPUB examples use a title paragraph or heading inside the same
            # example container. Bare pre blocks have no invented caption.
            for parent in tag.parents:
                if parent is root:
                    break
                classes = parent.get("class", [])
                if parent.get("data-type") == "example" or "example" in classes:
                    title = parent.find(["h5", "h6", "figcaption"]) or parent.find(class_="title")
                    if title:
                        block["caption"] = prose(title)
                        if refs := links(title):
                            block.setdefault("references", []).extend(refs)
                    break
            # Callouts are often outside the example container. Follow only
            # anchors explicitly attached to this pre, never another example.
            notes = []
            for anchor in tag.select("a.co[href]"):
                target = soup.find(id=anchor["href"].removeprefix("#"))
                dt = target.find_parent("dt") if target else None
                dd = dt.find_next_sibling("dd") if dt else None
                if dd:
                    note = {"label": prose(anchor), "text": prose(dd)}
                    if refs := links(dd):
                        note["references"] = refs
                    notes.append(note)
            if notes:
                block["annotations"] = notes
        out.append(block)
    return out


def select_chapter(payload: dict, *, code: bool, start: str | None, limit: int,
                   citation: bool = False) -> dict:
    all_blocks = blocks(payload["html"], payload["url"])
    offset = 0
    if start:
        # Match across inline markup and paragraph boundaries. A citation may
        # begin mid-sentence or end midway through an example caption.
        needle = normalise(start)
        joined = "".join(normalise(b["text"]) for b in all_blocks)
        pos = joined.find(needle)
        if pos < 0 and citation:
            # Search excerpts insert list markers and sometimes elide text.
            # A unique suffix still identifies where the excerpt ends.
            for size in (240, 160, 80, 40):
                suffix = needle[-size:]
                if len(suffix) >= 40 and joined.count(suffix) == 1:
                    needle = suffix
                    pos = joined.find(needle)
                    break
        if pos < 0:
            raise NotFound("cited passage/start text not found in chapter; read without --from-citation or use --start TEXT")
        end = pos + len(needle)
        total = 0
        for offset, block in enumerate(all_blocks):
            total += len(normalise(block["text"]))
            if total >= end:
                break
    selected = all_blocks[offset:]
    if code:
        selected = [b for b in selected if b["kind"] == "code"]
    else:
        # In prose mode the callout paragraphs already follow the example.
        selected = [{k: v for k, v in b.items() if k != "annotations"} for b in selected]
    return {k: v for k, v in payload.items() if k != "html"} | {
            "blocks": selected[:limit], "remaining_blocks": max(0, len(selected) - limit)}


def chapter_text(result: dict) -> str:
    reference = result.get("reference") or {}
    out = [part for part in [reference.get("title"), reference.get("chapter"),
                            ", ".join(reference.get("authors") or []), result["url"]] if part]
    for block in result["blocks"]:
        if block["kind"] == "code":
            if block.get("caption") and out[-1] != block["caption"]:
                out.append(block["caption"])
            # A longer fence also preserves examples which contain Markdown.
            runs = re.findall(r"`+", block["text"])
            fence = "`" * max(3, max((len(r) + 1 for r in runs), default=3))
            out.append(f"{fence}\n{block['text']}\n{fence}")
        else:
            out.append(block["text"])
        for ref in block.get("references", []):
            out.append(f"{ref['text']}: {ref['url']}")
        for note in block.get("annotations", []):
            out.append(f"{note['label']}. {note['text']}")
            for ref in note.get("references", []):
                out.append(f"{ref['text']}: {ref['url']}")
    if result["remaining_blocks"]:
        out.append(f"[{result['remaining_blocks']} more blocks; use --limit N or --start TEXT]")
    return "\n\n".join(out)
