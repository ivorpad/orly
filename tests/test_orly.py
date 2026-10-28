"""Tests for the pure logic. Every case here is a bug that actually happened."""

from __future__ import annotations

import io
import json
import sys

import pytest

from orly.api import same_host
from orly.auth import AUTH_COOKIES, HOST_FILTER, jwt_expiry
from orly.cli import EX_AUTH, EX_FAIL, EX_NOTFOUND, EX_TIMEOUT
from orly.commands import normalise_question
from orly.render import CITE, clean_quote, compact, flag_truncation


def test_exit_codes_are_distinct():
    """An agent picks retry-vs-pivot off these, so they must not collide."""
    codes = [0, 2, EX_FAIL, EX_NOTFOUND, EX_AUTH, EX_TIMEOUT]
    assert len(set(codes)) == len(codes)
    assert all(0 <= c < 256 for c in codes)


def header_names(cookie: str) -> set[str]:
    """The check cmd_auth runs on a pasted Cookie header."""
    return {p.split("=", 1)[0].strip() for p in cookie.split(";") if "=" in p}


def b64(payload: dict) -> str:
    import base64

    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"header.{raw}.signature"


@pytest.mark.parametrize("mode", ["--status", "--paste"])
def test_auth_with_saved_or_pasted_cookie_never_accesses_chrome(monkeypatch, capsys, mode):
    import io
    import sys
    from orly.cli import main

    cookie = f"orm-jwt={b64({'exp': 2000000000})}; orm-rt=opaque-refresh-token"

    def forbidden(*args, **kwargs):
        pytest.fail("saved/pasted auth must not access Chrome, SQLite, or the Keychain")

    for name in ("chrome_profiles", "keychain_password", "cookies_from_chrome"):
        monkeypatch.setattr(f"orly.auth.{name}", forbidden)
    monkeypatch.setattr("orly.commands.cookies_from_chrome", forbidden)
    monkeypatch.setattr("orly.auth.shutil.copy2", forbidden)
    monkeypatch.setattr("orly.auth.sqlite3.connect", forbidden)
    monkeypatch.setattr("orly.commands.load_cookie", lambda: cookie)
    monkeypatch.setattr("orly.commands.save_cookie", lambda value: None)

    class FakeAnswers:
        def __init__(self, value):
            assert value == cookie

        def history(self, count):
            assert count == 1
            return []

    monkeypatch.setattr("orly.commands.Answers", FakeAnswers)
    monkeypatch.setattr(sys, "stdin", io.StringIO(cookie + "\n"))
    monkeypatch.setattr(sys, "argv", ["orly", "auth", mode])
    assert main() == 0
    assert "expiry unavailable from saved cookie" in capsys.readouterr().out


class Terminal(io.StringIO):
    """stdin the way a person at a terminal gives it."""

    def isatty(self):
        return True


@pytest.mark.parametrize(
    "stdin",
    [io.StringIO("yes\n"), Terminal("no\n"), Terminal("y\n"), Terminal("")],
    ids=["piped yes", "typed no", "typed y", "end of input"],
)
def test_chrome_import_reads_nothing_without_a_typed_yes(monkeypatch, capsys, stdin):
    """A corporate Mac must never read browser cookies. An agent or a pipe has
    no terminal to answer from, and anything short of yes stops before Chrome's
    profile folder is even listed."""
    from orly.cli import main

    def forbidden(*args, **kwargs):
        pytest.fail("Chrome must not be touched before someone types yes")

    for name in ("chrome_profiles", "keychain_password"):
        monkeypatch.setattr(f"orly.auth.{name}", forbidden)
    monkeypatch.setattr("orly.auth.shutil.copy2", forbidden)
    monkeypatch.setattr("orly.auth.sqlite3.connect", forbidden)
    monkeypatch.setattr("orly.commands.save_cookie", forbidden)
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "argv", ["orly", "auth", "--chrome"])
    assert main() == EX_AUTH
    # rich wraps stderr at 80 columns, so compare with the line breaks folded.
    assert "Nothing was read." in " ".join(capsys.readouterr().err.split())


@pytest.mark.parametrize("answer", ["yes\n", " Yes \n"])
def test_chrome_import_goes_ahead_once_yes_is_typed(monkeypatch, capsys, answer):
    from orly.auth import AuthError
    from orly.cli import main

    reached = []

    def chrome_profiles():
        reached.append(True)
        raise AuthError("stopped at chrome_profiles")

    monkeypatch.setattr("orly.auth.chrome_profiles", chrome_profiles)
    monkeypatch.setattr(sys, "stdin", Terminal(answer))
    monkeypatch.setattr(sys, "argv", ["orly", "auth", "--chrome"])
    assert main() == EX_AUTH
    assert reached == [True]
    assert "stopped at chrome_profiles" in capsys.readouterr().err


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_auth_failures_suggest_paste_before_chrome(monkeypatch, tmp_path, platform):
    """An agent tries the first fix it is given. On a Mac that must not read
    browser cookies, that has to be the paste."""
    import httpx
    from orly.api import BASE, Answers
    from orly.auth import AuthError, load_cookie

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.delenv("ORLY_COOKIE", raising=False)
    monkeypatch.setattr("orly.auth.COOKIE_FILE", tmp_path / "cookie")
    with pytest.raises(AuthError) as missing:
        load_cookie()

    api = Answers("orm-jwt=a; orm-rt=b", persist=False)
    with pytest.raises(AuthError) as rejected:
        api._check(httpx.Response(401, request=httpx.Request("GET", BASE)))
    api.http.close()

    for raised in (missing, rejected):
        text = str(raised.value)
        assert ("--chrome" in text) == (platform == "darwin")
        if platform == "darwin":
            assert text.index("orly auth --paste") < text.index("orly auth --chrome")
            assert "type yes" in text


class TestFlagTruncation:
    """An agent handed `...backup jobs at specifi` completed it to
    `at specifi[c intervals]` and presented that as a direct quote."""

    @pytest.mark.parametrize(
        "text",
        [
            "set up backup jobs at specifi",
            "the connection pool will even",
            "trailing whitespace cut   ",
        ],
    )
    def test_marks_a_cut_passage(self, text):
        assert "truncated mid-sentence" in flag_truncation(text)

    @pytest.mark.parametrize(
        "text",
        [
            "A complete sentence.",
            "Ends in a question?",
            "Emphatic!",
            'Closing quote."',
            "Already elided...",
        ],
    )
    def test_leaves_complete_passages_alone(self, text):
        assert flag_truncation(text) == text

    def test_empty_stays_empty(self):
        assert flag_truncation("") == ""
        assert flag_truncation(None) == ""


class TestCleanQuote:
    def test_strips_mark_tags_and_unescapes(self):
        raw = "the <mark>WAL</mark> is append&#45;only &amp; durable"
        assert clean_quote(raw) == "the WAL is append-only & durable"

    def test_collapses_the_hard_wraps_books_arrive_with(self):
        assert clean_quote("a line\n   and its\n\n continuation") == "a line and its continuation"


class TestCitations:
    def test_footnotes_collapse_to_plain_markers(self):
        src = "Sharding splits data.[[^1]](https://example.com/a) It scales.[[^2]](https://x/b)"
        assert CITE.sub(r"[\1]", src) == "Sharding splits data.[1] It scales.[2]"


class TestJwtExpiry:
    def test_reads_the_exp_claim(self):
        assert jwt_expiry(b64({"exp": 1785954739})) == 1785954739.0

    @pytest.mark.parametrize("bad", ["", "not.a.jwt", "onlyonepart", b64({"no": "exp"})])
    def test_returns_none_rather_than_raising(self, bad):
        assert jwt_expiry(bad) is None


class TestPastedHeader:
    """Either auth cookie alone is a 401, so a partial paste must be rejected
    at the door rather than saved and failing later against the API."""

    def test_a_full_browser_header_passes(self):
        raw = "_abck=x; groot_sessionid=abc; orm-jwt=eyJhb.cD.ef; orm-rt=deadbeef; _ga=1"
        assert not [c for c in AUTH_COOKIES if c not in header_names(raw)]

    @pytest.mark.parametrize(
        "raw,absent",
        [
            ("orm-jwt=abc; other=x", "orm-rt"),
            ("orm-rt=abc", "orm-jwt"),
            ("groot_sessionid=abc", "orm-jwt"),  # looks like a session, is not
            ("", "orm-jwt"),
        ],
    )
    def test_a_partial_paste_is_caught(self, raw, absent):
        assert absent in [c for c in AUTH_COOKIES if c not in header_names(raw)]

    def test_whitespace_around_names_is_tolerated(self):
        raw = "  orm-jwt=a ;  orm-rt=b  "
        assert not [c for c in AUTH_COOKIES if c not in header_names(raw)]


class TestSameHost:
    """`next` in a paginated response is server-controlled, and the jar has no
    domain, so an off-host URL followed here would hand over the session."""

    @pytest.mark.parametrize(
        "url",
        [
            "/user-question-history/",              # ours, relative to base_url
            "/user-question-history/?page=2",
            "https://learning.oreilly.com/api/v1/x/?page=2",
        ],
    )
    def test_allows_our_own_urls(self, url):
        assert same_host(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.net/page2",
            "//evil.example.net/x",                       # protocol-relative
            "https://learning.oreilly.com.attacker.io/x",  # suffix, not the host
            "https://notoreilly.com/x",
            "http://learning.oreilly.com/x",               # right host, cleartext
        ],
    )
    def test_refuses_anywhere_else(self, url):
        assert not same_host(url)


class TestCookieHostFilter:
    """`LIKE '%oreilly.com'` also matched domains anyone can register, whose
    cookies would then be posted to learning.oreilly.com."""

    @pytest.fixture
    def match(self):
        """Run the real WHERE clause against one host_key at a time."""
        import sqlite3

        con = sqlite3.connect(":memory:")
        sql = f"SELECT EXISTS(SELECT 1 FROM (SELECT ? AS host_key) WHERE {HOST_FILTER})"
        return lambda host: bool(con.execute(sql, (host,)).fetchone()[0])

    @pytest.mark.parametrize(
        "host", ["learning.oreilly.com", ".oreilly.com", "oreilly.com", "www.oreilly.com"]
    )
    def test_keeps_real_oreilly_hosts(self, match, host):
        assert match(host)

    @pytest.mark.parametrize(
        "host", ["notoreilly.com", "evil-oreilly.com", "oreilly.com.attacker.io"]
    )
    def test_drops_lookalikes(self, match, host):
        assert not match(host)


class TestNormaliseQuestion:
    """--reuse matches on this. Too loose and it hands back the wrong answer;
    too tight and it never fires, which is how it shipped the first time."""

    def test_punctuation_and_case_do_not_matter(self):
        assert normalise_question("What is a bloom filter?") == normalise_question(
            "what is a bloom filter"
        )

    def test_whitespace_is_collapsed(self):
        assert normalise_question("  what  is\na bloom filter ") == "what is a bloom filter"

    def test_different_questions_stay_different(self):
        assert normalise_question("what is a bloom filter") != normalise_question(
            "what is a cuckoo filter"
        )

    def test_negation_is_not_normalised_away(self):
        assert normalise_question("when to use event sourcing") != normalise_question(
            "when not to use event sourcing"
        )

    def test_handles_empty(self):
        assert normalise_question("") == ""
        assert normalise_question(None) == ""


class TestCompact:
    """Compact JSON omits catalog HTML blurbs and request configuration."""

    @pytest.fixture
    def record(self):
        return {
            "question_id": "abc123",
            "question": "why?",
            "created_time": "2026-08-05T18:00:00Z",
            "miso_response": {
                "data": {
                    "answer": "Because.[[^1]](https://example.com/x)",
                    "sources": [
                        {
                            "title": "Some Book",
                            "child_title": "3. A Chapter",
                            "authors": ["A Writer"],
                            "date": "2024-01-01T00:00:00+00:00",
                            "child_url": "https://example.com/ch3",
                            "url": "https://example.com/book",
                            "highlight_text": "A quoted passage that ends properly.",
                            "html": "<p>" + "x" * 20000 + "</p>",
                        }
                    ],
                    "followup_questions": ["and then?"],
                }
            },
        }

    def test_drops_the_html_payload(self, record):
        assert "x" * 100 not in json.dumps(compact(record))

    def test_keeps_what_a_citation_needs(self, record):
        s = compact(record)["sources"][0]
        assert s["title"] == "Some Book"
        assert s["chapter"] == "3. A Chapter"
        assert s["authors"] == ["A Writer"]
        assert s["year"] == "2024"
        assert s["url"] == "https://example.com/ch3"  # deep link beats the book url
        assert s["quote"] == "A quoted passage that ends properly."

    def test_flags_truncation_in_json_too(self, record):
        record["miso_response"]["data"]["sources"][0]["highlight_text"] = "cut off at specifi"
        assert "truncated mid-sentence" in compact(record)["sources"][0]["quote"]

    def test_normalises_citations_in_the_answer(self, record):
        assert compact(record)["answer"] == "Because.[1]"

    def test_survives_an_empty_record(self):
        out = compact({})
        assert out["answer"] == ""
        assert out["sources"] == []
