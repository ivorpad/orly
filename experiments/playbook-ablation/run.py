"""Cache five book cases sequentially, then ablate chapter extraction offline.

Run with `uv run python experiments/playbook-ablation/run.py`.
Private source payloads stay under ignored .agent/, outside the report.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from orly.api import Answers, NotFound
from orly.auth import load_cookie
from orly.chapter import blocks, normalise, select_chapter
from orly.render import clean_quote, compact

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".agent/playbook-ablation"
OUT = Path(__file__).resolve().parent
CASES = [
    ("python", "Fluent Python, 2nd Edition", "fluent python", "Implement a Python context manager that releases a resource even if the with body raises an exception. Explain __exit__ exception suppression using a concrete code example."),
    ("rust", "Programming Rust, 2nd Edition", "programming rust", "Propagate recoverable errors with Result and the ? operator rather than panic, using a concrete Rust code example."),
    ("go", "Learning Go, 2nd Edition", "learning go", "Use defer to close an opened file while handling an os.Open error, using a concrete Go code example."),
    ("java", "Effective Java, 3rd Edition", "effective java", "Use try-with-resources rather than try-finally to close resources safely and preserve exceptions, using a concrete Java code example."),
    ("javascript", "JavaScript: The Definitive Guide, 7th Edition", "javascript: the definitive guide", "Handle rejected promises with async/await and try/catch, using a concrete JavaScript code example."),
]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


class PacedTransport(httpx.BaseTransport):
    """One request at a time, minimum five seconds between request starts."""

    def __init__(self):
        self.inner = httpx.HTTPTransport(retries=0)
        self.last = 0.0
        log = CACHE / "requests.json"
        self.events = json.loads(log.read_text()) if log.exists() else []

    def handle_request(self, request):
        for attempt in range(4):
            time.sleep(max(0, self.last + 5 - time.monotonic()))
            self.last = time.monotonic()
            response = self.inner.handle_request(request)
            event = {"time": datetime.now(timezone.utc).isoformat(),
                     "method": request.method, "path": request.url.path,
                     "status": response.status_code, "attempt": attempt + 1}
            self.events.append(event)
            write(CACHE / "requests.json", self.events)
            if response.status_code != 429:
                return response
            raw = response.headers.get("Retry-After", "")
            try:
                delay = max(0, float(raw))
            except ValueError:
                try:
                    delay = max(0, (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError):
                    delay = 60 * (2 ** attempt)
            event["retry_after_seconds"] = delay
            write(CACHE / "requests.json", self.events)
            if request.method != "GET" or attempt == 3:
                return response  # Never automatically resubmit a question.
            response.close()
            print(f"Rate limited; waiting {delay:.0f}s before retrying GET", flush=True)
            time.sleep(delay)
        raise AssertionError("unreachable")

    def close(self):
        self.inner.close()


def code_locations(html):
    soup = BeautifulSoup(html, "html.parser")
    for image in soup.select("a.co img[alt]"):
        image.replace_with(image["alt"])
    result = {}
    for pre in soup.find_all("pre"):
        text = pre.get_text("", strip=False).strip("\n")
        own = pre.get("id")
        parent = next((p.get("id") for p in pre.parents if p.get("id")), None)
        result[normalise(text)] = {"own_anchor": own, "ancestor_anchor": parent}
    return result


def run():
    CACHE.mkdir(parents=True, exist_ok=True)
    api = Answers(load_cookie(), timeout=60)
    paced = PacedTransport()
    old = api.http
    api.http = httpx.Client(base_url=old.base_url, headers=old.headers,
                            cookies=old.cookies, timeout=60, follow_redirects=False,
                            transport=paced)
    old.close()
    results = []
    try:
        for language, book, title_match, task in CASES:
            folder = CACHE / language
            folder.mkdir(exist_ok=True)
            answer_path = folder / "answer.json"
            if answer_path.exists():
                answer = json.loads(answer_path.read_text())
            else:
                qid_path = folder / "question-id.txt"
                if qid_path.exists():
                    qid = qid_path.read_text().strip()
                else:
                    question = f"Using {book} specifically: {task} Cite the relevant passage and book chapter containing the example."
                    qid = api.ask(question)
                    qid_path.write_text(qid + "\n")
                print(f"{language}: waiting for {qid[:8]}", flush=True)
                answer = compact(api.wait(qid, timeout=240))
                write(answer_path, answer)
            candidates = [s for s in answer["sources"] if re.search(r"\.(?:html|xhtml|htm)(?:[?#]|$)", s.get("url") or "")]
            sources = [s for s in candidates if title_match in s["title"].casefold()]
            retrieval_note = None
            if not sources and candidates:
                sources = candidates[:1]
                retrieval_note = "Requested title had no usable chapter citation; selected the alternate book chapter returned in the same answer."
            if not sources:
                print(f"{language}: requested book not retrieved", flush=True)
                results.append({"language": language, "requested_book": book,
                                "status": "book_not_retrieved", "question_id": answer["question_id"]})
                continue
            source = sources[0]
            chapter_path = folder / "chapter.json"
            if chapter_path.exists():
                payload = json.loads(chapter_path.read_text())
            else:
                try:
                    payload = api.chapter(source["url"])
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 406:
                        print(f"{language}: HTML Accept rejected; trying Accept */* once", flush=True)
                        def accept_any(request):
                            request.headers["Accept"] = "*/*"
                        api.http.event_hooks["request"].append(accept_any)
                        try:
                            payload = api.chapter(source["url"])
                            write(folder / "fetch-workaround.json", {"initial_status": 406, "accept": "*/*"})
                        except (httpx.HTTPStatusError, RuntimeError) as retry_error:
                            results.append({"language": language, "requested_book": book,
                                "source": source, "status": "chapter_fetch_failed",
                                "error": str(retry_error), "question_id": answer["question_id"]})
                            print(f"{language}: chapter fetch failed", flush=True)
                            continue
                        finally:
                            api.http.event_hooks["request"].remove(accept_any)
                    else:
                        raise
                write(chapter_path, payload)
            payload["reference"] = {"title": source["title"], "chapter": source["chapter"],
                                    "authors": source["authors"], "answer_id": answer["question_id"],
                                    "source": source["n"]}
            all_blocks = blocks(payload["html"], payload["url"])
            variants = {}
            selections = {}
            for variant, code, start, citation in [
                ("B_default12", False, None, False),
                ("C_code12", True, None, False),
                ("D_citation_code12", True, clean_quote(source.get("quote", "").split("[... truncated")[0]), True),
                ("E_citation_mixed12", False, clean_quote(source.get("quote", "").split("[... truncated")[0]), True),
            ]:
                try:
                    selected = select_chapter(payload, code=code, start=start,
                                              citation=citation, limit=12)
                    selections[variant] = selected
                    write(folder / f"{variant}.json", selected)
                    cb = [b for b in selected["blocks"] if b["kind"] == "code"]
                    variants[variant] = {"status": "ok", "blocks": len(selected["blocks"]),
                        "code_blocks": len(cb), "captions": sum(bool(b.get("caption")) for b in cb),
                        "annotations": sum(len(b.get("annotations", [])) for b in cb),
                        "characters": sum(len(b["text"]) for b in selected["blocks"]),
                        "remaining_blocks": selected["remaining_blocks"]}
                except NotFound as exc:
                    variants[variant] = {"status": "anchor_not_found", "message": str(exc)}
            variants["A_citation_only"] = {"status": "ok", "characters": len(source.get("quote", "")),
                                            "has_preformatted_code": "```" in source.get("quote", "")}
            locations = code_locations(payload["html"])
            catalog = []
            for i, block in enumerate(all_blocks):
                if block["kind"] != "code":
                    continue
                loc = locations.get(normalise(block["text"]), {})
                catalog.append({"block_index": i, "sha256": hashlib.sha256(block["text"].encode()).hexdigest(),
                                "caption": block.get("caption"), "characters": len(block["text"]),
                                "preview": block["text"][:160], **loc})
            write(folder / "code-catalog.json", catalog)
            result = {"language": language, "requested_book": book, "task": task, "status": "ok",
                "retrieval_note": retrieval_note,
                "question_id": answer["question_id"], "source": source,
                "chapter_sha256": hashlib.sha256(payload["html"].encode()).hexdigest(),
                "chapter_code_blocks": len(catalog), "variants": variants,
                "chapter_anchor_count": sum(bool(c.get("own_anchor") or c.get("ancestor_anchor")) for c in catalog)}
            results.append(result)
            write(CACHE / "results.json", results)
            print(f"{language}: {source['title']}; {len(catalog)} code blocks; "
                  f"citation extraction={variants['D_citation_code12']['status']}", flush=True)
    finally:
        api.http.close()
        write(CACHE / "results.json", results)
    print("Done. Source payloads cached locally; no browser access.", flush=True)


if __name__ == "__main__":
    run()
