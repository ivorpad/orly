"""HTTP client for the Answers relay service.

Private, undocumented API. Two behaviours drive the design: there is no
streaming (the answer field is empty until it is complete), and a freshly
posted question 404s for a couple of seconds before its record exists.
"""

from __future__ import annotations

import sys
import time

import httpx

from .auth import AuthError, save_cookie

BASE = "https://learning.oreilly.com/api/v1/miso-answers-relay-service"

FQ = (
    '(type:book OR type:article OR type:video) AND language:("en" OR "EN" OR '
    '"en-au" OR "en-gb" OR "en-GB" OR "en-us" OR "en-US")'
)

FIELDS = [
    "custom_attributes.ourn",
    "custom_attributes.publishers",
    "custom_attributes.marketing_type*",
    "custom_attributes.required_p_permissions",
    "url",
    "cover_image",
    "authors",
    "html",
]


class Answers:
    """Client for the Answers relay service.

    Auth is `orm-jwt` (a short-lived access JWT) plus `orm-rt` (the refresh
    token). The gateway re-issues BOTH on every response, so the jar has to be
    written back or the stored session slowly goes stale.
    """

    def __init__(self, cookie: str, timeout: float = 30.0, persist: bool = True):
        self._jar = dict(p.split("=", 1) for p in cookie.split("; ") if "=" in p)
        self._persist = persist
        self.http = httpx.Client(
            base_url=BASE,
            timeout=timeout,
            follow_redirects=False,
            cookies=self._jar,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Referer": "https://learning.oreilly.com/answers2/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
                ),
            },
        )

    def flush_cookies(self) -> bool:
        """Write refreshed tokens back to disk. Returns True if anything moved."""
        if not self._persist:
            return False
        # dict(client.cookies) raises CookieConflict when a name (e.g. _abck)
        # exists for several domains, so walk the jar and let the
        # oreilly.com-scoped entry win.
        current: dict[str, str] = {}
        for c in sorted(
            self.http.cookies.jar, key=lambda c: "oreilly.com" in (c.domain or "")
        ):
            if c.value is not None:
                current[c.name] = c.value
        if not current or current == self._jar:
            return False
        merged = {**self._jar, **current}
        if merged == self._jar:
            return False
        self._jar = merged
        try:
            save_cookie("; ".join(f"{k}={v}" for k, v in merged.items()))
        except OSError:
            return False
        return True

    def _check(self, r: httpx.Response) -> httpx.Response:
        self.flush_cookies()
        if r.status_code in (401, 403):
            raise AuthError(
                f"O'Reilly rejected the session cookie (HTTP {r.status_code}).\n"
                + (
                    "Re-run:  orly auth --chrome\n"
                    "If that keeps failing, sign in to learning.oreilly.com in "
                    "Chrome first."
                    if sys.platform == "darwin"
                    else "Refresh it with:  orly auth --paste\n"
                    "(run `orly auth --paste` with no input piped for instructions)"
                )
            )
        r.raise_for_status()
        return r

    def ask(self, question: str, source_page: str = "answers") -> str:
        payload = {
            "fq": FQ,
            "source_fl": FIELDS,
            "related_resource_fl": FIELDS,
            "cite_link": True,
            # The web app sends 500/200. Both are honoured up to at least
            # 1500/1200, and at 200 the cited passage is routinely chopped
            # mid-word ("...set up backup jobs at specifi"). A caller quoting
            # that has to either drop the sentence or invent its ending, and
            # agents invent. Ask for room to finish the thought.
            "_pipeline_config": {
                "snippet_length": 1500,
                "highlight_length": 1200,
                "version": "v3",
            },
            "question": question,
            "query_source": "original",
            "question_source_page": source_page,
            "answer_render_page": source_page,
        }
        r = self._check(self.http.post("/questions/", json=payload))
        return r.json()["question_id"]

    def get(self, qid: str) -> dict | None:
        """Fetch a question. Returns None while the record is still being created.

        A freshly POSTed question 404s for a second or two before it lands in
        the history table.
        """
        r = self.http.get(f"/user-question-history/{qid}/")
        if r.status_code == 404:
            self.flush_cookies()
            return None
        return self._check(r).json()

    def history(self, limit: int = 20) -> list[dict]:
        out: list[dict] = []
        url = "/user-question-history/"
        while url and len(out) < limit:
            page = self._check(self.http.get(url)).json()
            out.extend(page.get("results", []))
            url = page.get("next")
        return out[:limit]

    def wait(self, qid: str, timeout: float = 180.0, on_stage=None) -> dict:
        """Poll until the answer is finished. There is no streaming endpoint."""
        deadline = time.monotonic() + timeout
        appear_by = time.monotonic() + max(30.0, min(120.0, timeout / 2))
        delay = 1.0
        while True:
            rec = self.get(qid)
            if rec is None:
                if time.monotonic() > appear_by:
                    raise RuntimeError(
                        f"Question {qid} has not appeared yet.\n"
                        f"It WAS created, so nothing is lost: it is still being "
                        f"written, which happens when several asks run at once.\n"
                        f"Recover it with:  orly show {qid[:8]}"
                    )
                if on_stage:
                    on_stage("Submitting")
            else:
                if rec.get("is_finished"):
                    return rec
                if msg := rec.get("error_message"):
                    raise RuntimeError(f"O'Reilly returned an error: {msg}")
                if on_stage:
                    data = (rec.get("miso_response") or {}).get("data") or {}
                    on_stage(data.get("answer_stage") or "Thinking")
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Answer not ready after {timeout:.0f}s (question {qid})"
                )
            time.sleep(delay)
            delay = min(delay * 1.35, 4.0)


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

