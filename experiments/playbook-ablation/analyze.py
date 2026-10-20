"""Offline scoring and Markdown playbooks from the cached five-book experiment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bs4 import BeautifulSoup

from orly.chapter import blocks, normalise
from run import CACHE, OUT, write

# Human-reviewed examples addressing each task. These are relevance labels,
# not a semantic search algorithm and not measurements of executable correctness.
LABELS = {
    "python": {"relevant": [44, 115], "chosen": 44,
        "rule": "Restore the original resource state in __exit__; return a truthy value only for an exception intentionally handled.",
        "verify": ["Normal completion restores sys.stdout.write.", "A ZeroDivisionError is handled by this example; another exception propagates after restoration."],
        "decision": "Which exception types, if any, should the application suppress?",
        "label": "Example 18-3, mirror.py"},
    "rust": {"relevant": [77, 88], "chosen": 88,
        "rule": "Return Result and use ? at fallible operations to propagate recoverable errors to the caller.",
        "verify": ["Directory-open, directory-entry, and rename errors return Err.", "The success path returns Ok(())."],
        "decision": "Where should the caller handle and report the propagated error?",
        "label": "Propagating Errors, move_all"},
    "go": {"relevant": [232, 237], "chosen": 232,
        "rule": "Put per-file work in a helper so defer file.Close() runs on each iteration's helper return; check os.Open before registering cleanup.",
        "verify": ["Each completed iteration closes its file before the next one proceeds.", "An open failure returns its error without using a nil file."],
        "decision": "How should file.Close errors be handled? This excerpt explicitly defers that topic to mistake #54.",
        "label": "Mistake #35, readFiles/readFile helper solution"},
    "java": {"relevant": [224, 227, 231], "chosen": 224,
        "rule": "Use try-with-resources for AutoCloseable resources so cleanup occurs on return and exceptions while preserving the primary failure.",
        "verify": ["The reader closes after both successful reads and read failures.", "If reading and closing both throw, the read exception remains primary and the close exception is suppressed."],
        "decision": "Should the caller propagate IOException or choose an explicit fallback?",
        "label": "Item 9, firstLineOfFile using try-with-resources"},
    "javascript": {"relevant": [], "chosen": None,
        "rule": "Await the asynchronous work inside try and handle rejection in catch; rejected awaited promises throw into that handler.",
        "verify": ["The rejected third promise reaches catch with Oh no!.", "Fulfilled awaited promises proceed without entering catch."],
        "decision": "Should catch recover, report, or rethrow? The book example logs the error.",
        "label": "Snippet 2.38: Error handling"},
}


def snippet_adapter(html):
    """Prototype only: group contiguous p.snippet lines, keeping their caption.

    Not shipped in orly. Line text is preserved, including nonbreaking spaces.
    """
    soup = BeautifulSoup(html, "html.parser")
    for start in list(soup.select("p.snippet")):
        if start.parent is None:
            continue
        group = [start]
        nxt = start.find_next_sibling()
        while nxt is not None and nxt.name == "p" and "snippet" in nxt.get("class", []):
            group.append(nxt)
            nxt = nxt.find_next_sibling()
        wrapper = soup.new_tag("div", attrs={"data-type": "example"})
        start.insert_before(wrapper)
        if nxt is not None and nxt.name == "h6":
            wrapper.append(nxt.extract())
        pre = soup.new_tag("pre")
        pre.string = "\n".join(p.get_text("", strip=False) for p in group)
        wrapper.append(pre)
        for p in group:
            p.decompose()
    return str(soup)


def locate(html, text):
    soup = BeautifulSoup(html, "html.parser")
    for image in soup.select("a.co img[alt]"):
        image.replace_with(image["alt"])
    for pre in soup.find_all("pre"):
        if normalise(pre.get_text("", strip=False)) != normalise(text):
            continue
        # Prefer the example container to numeric callout IDs inside O'Reilly
        # examples. Manning uses line anchors; Pearson uses preceding image IDs.
        ancestors = [p for p in pre.parents if p.get("id") and p.get("id") != "sbo-rt-content"
                     and len(p.find_all("pre")) <= 10]
        descendant = pre.find(id=True)
        sibling = pre.find_previous_sibling()
        adjacent_anchor = sibling.find(id=True) if sibling else None
        heading = next((h for h in pre.find_all_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
                        if h.get("id")), None)
        previous = pre.find_previous(id=True)
        anchor = (pre.get("id") or (ancestors[0]["id"] if ancestors else None)
                  or (descendant["id"] if descendant else None)
                  or (adjacent_anchor["id"] if adjacent_anchor else None)
                  or (heading["id"] if heading else None)
                  or (previous["id"] if previous else None))
        return anchor
    return None


def main():
    rows = json.loads((CACHE / "results.json").read_text())
    public = []
    destination = OUT / "playbooks"
    destination.mkdir(exist_ok=True)
    for row in rows:
        language = row["language"]
        label = LABELS[language]
        payload = json.loads((CACHE / language / "chapter.json").read_text())
        original = blocks(payload["html"], payload["url"])
        target_texts = {original[i]["text"] for i in label["relevant"]}
        scored = {}
        for variant in ["B_default12", "C_code12", "D_citation_code12", "E_citation_mixed12"]:
            metric = row["variants"][variant].copy()
            if metric["status"] == "ok":
                selected = json.loads((CACHE / language / f"{variant}.json").read_text())["blocks"]
                metric["relevant_code"] = any(b["kind"] == "code" and b["text"] in target_texts for b in selected)
            else:
                metric["relevant_code"] = False
            scored[variant] = metric
        html = payload["html"]
        if language == "javascript":
            html = snippet_adapter(html)
            adapted = blocks(html, payload["url"])
            chosen = next(b for b in adapted if b.get("caption") == label["label"] and b["kind"] == "code")
            # This is a recovered format, not a successful current-CLI variant.
            original_snippets = BeautifulSoup(payload["html"], "html.parser").select("p.snippet")
            expected = "\n".join(p.get_text("", strip=False) for p in original_snippets[264:278])
            assert chosen["text"] == expected
            excerpt_origin = "Contiguous p.snippet paragraphs joined with newlines; prototype adapter, absent from the released parser."
        else:
            chosen = original[label["chosen"]]
            excerpt_origin = "Verbatim current-parser output; book callout markers and whitespace are retained."
        anchor = locate(html, chosen["text"])
        assert anchor is not None
        assert BeautifulSoup(payload["html"], "html.parser").find(id=anchor) is not None
        url = payload["url"] + "#" + anchor
        digest = hashlib.sha256(chosen["text"].encode()).hexdigest()
        source = row["source"]
        display = "JavaScript" if language == "javascript" else language.title()
        chunks = [f"# {display}: {label['label']}",
                  "## Feedforward", label["rule"], "## Code reference",
                  f"[{source['title']} · {label['label']}]({url})",
                  f"```{language}\n{chosen['text']}\n```", excerpt_origin,
                  f"Extracted code SHA-256: `{digest}`.",
                  "## Feedback", "\n".join("- " + item for item in label["verify"]),
                  "## Decision required", label["decision"],
                  "## Evidence boundary", "Rules and checks are agent synthesis from the cited example and adjacent explanation. Checks are proposed acceptance criteria; they were not executed. The excerpt is reference material, not a standalone program."]
        if language in {"python", "go"}:
            chunks.append("Book callout numerals appear inside the excerpt. Keep them as annotations when adapting the code; this fenced reference is not directly pasteable source.")
        (destination / f"{language}.md").write_text("\n\n".join(chunks) + "\n")
        public.append({"language": language, "book": source["title"], "chapter": source["chapter"],
                       "question_id": row["question_id"], "requested_book": row["requested_book"],
                       "retrieval_note": row.get("retrieval_note"),
                       "chapter_sha256": row["chapter_sha256"],
                       "code_blocks_in_chapter": row["chapter_code_blocks"],
                       "variants": scored, "reviewed_relevant_block_indices": label["relevant"],
                       "curated_code_reference": {"url": url, "label": label["label"], "sha256": digest},
                       "prototype_adapter_used": language == "javascript"})
    requests = json.loads((CACHE / "requests.json").read_text())
    write(OUT / "results.json", {"date": "2026-10-20", "block_limit": 12,
        "scoring": "Human-reviewed relevance labels; exact extracted-code matching. No execution or coding-agent task benchmark.",
        "requests": {"total": len(requests), "question_submissions": sum(r["method"] == "POST" for r in requests),
                     "http_429": sum(r["status"] == 429 for r in requests),
                     "http_406": sum(r["status"] == 406 for r in requests),
                     "minimum_request_start_spacing_seconds": 5}, "cases": public})
    for row in public:
        print(row["language"], {k: v["relevant_code"] for k, v in row["variants"].items()}, row["curated_code_reference"]["url"])
    print("Offline analysis complete; all five references validated against cached HTML IDs.")


if __name__ == "__main__":
    main()
