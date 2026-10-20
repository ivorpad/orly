"""Offline harness evidence contracts across the EPUB layouts seen in practice."""

import ast
import io
import json
import sys

import httpx
import pytest

from orly.api import UsageError, NotFound
from orly.evidence import extract, markdown
from orly.cli import main

URL = "https://learning.oreilly.com/library/view/-/isbn/chapter.html"


def chapter(html):
    return {"url": URL, "html": html}


def excerpts(html):
    payload = chapter(html)
    index = extract(payload)
    return extract(payload, [e["id"] for e in index["entries"]], index["chapter_sha256"])


def test_example_callouts_are_separate_from_clean_code():
    html = '''<div data-type="example" id="sample"><h5>Example 1</h5>
    <pre>def f(): <a class="co" href="#n"><img alt="1"></a>
    return 1</pre></div>
    <dl><dt><a class="co" id="n">1</a></dt><dd><p>A function.</p></dd></dl>'''
    index = extract(chapter(html))
    example, = excerpts(html)["entries"]
    ast.parse(example["code"])
    assert example["url"] == URL + "#sample"
    assert example["reference_scope"] == "example"
    assert example["annotations"] == [{"label": "1", "text": "A function."}]
    assert "removed callout markers" in example["transformations"]
    assert "code" not in index["entries"][0]


def test_snippet_paragraphs_keep_lines_indentation_and_following_caption():
    html = '''<h3 id="async">Async</h3><p>Await before handling rejection.</p>
    <p class="snippet">async function run() {</p>
    <p class="snippet">\u00a0\u00a0await task();</p>
    <p class="snippet">}</p><h6>Snippet 2.38: Error handling</h6>'''
    entry, = excerpts(html)["entries"]
    assert entry["code"] == "async function run() {\n  await task();\n}"
    assert entry["caption"] == "Snippet 2.38: Error handling"
    assert entry["url"] == URL + "#async"
    assert entry["reference_scope"] == "section"


def test_line_anchors_and_circled_callouts():
    html = '''<h2>Using defer inside loops</h2>
    <pre><a id="line1"></a>defer file.Close() <span class="fm-combinumeral">❶</span></pre>
    <p>❶ Close at function return.</p><p>Regular explanation.</p>'''
    entry, = excerpts(html)["entries"]
    assert entry["url"] == URL + "#line1"
    assert entry["reference_scope"] == "line"
    assert "❶" not in entry["code"]
    assert entry["annotations"] == [{"label": "❶", "text": "Close at function return."}]
    assert "Regular explanation." in entry["context_after"]


def test_preceding_code_image_anchor_and_nonbreaking_spaces():
    html = '''<h3>Item 9</h3><p><a id="example9">View code image</a></p>
    <pre>try (Reader r = open()) {\n\u00a0\u00a0return r.read();\n}</pre>'''
    entry, = excerpts(html)["entries"]
    assert entry["url"] == URL + "#example9"
    assert "\n  return" in entry["code"]
    assert entry["section"] == "Item 9"


def test_rust_style_section_and_context_on_both_sides():
    html = '''<section id="propagate"><h2>Propagating errors</h2>
    <p>Return Result to the caller.</p><pre>let result = fallible()?;</pre>
    <p>Errors return early.</p></section>'''
    entry, = excerpts(html)["entries"]
    assert entry["url"] == URL + "#propagate"
    assert "Return Result to the caller." in entry["context_before"]
    assert "Errors return early." in entry["context_after"]


def test_missing_anchor_has_explicit_chapter_reference_scope():
    entry, = excerpts("<pre>work()</pre>")["entries"]
    assert entry["url"] == URL
    assert entry["reference_scope"] == "chapter"


def test_no_code_is_an_explicit_gap():
    result = extract(chapter("<p>Only prose.</p>"))
    assert result["entries"] == [] and result["gaps"]
    assert "Evidence gap:" in markdown(result)


def test_snapshot_guard_prevents_stale_block_selection():
    index = extract(chapter("<pre>first()</pre>"))
    with pytest.raises(UsageError, match="snapshot changed"):
        extract(chapter("<pre>second()</pre>"), ["b0"], index["chapter_sha256"])
    with pytest.raises(NotFound, match="unknown code block"):
        extract(chapter("<pre>first()</pre>"), ["b999"])


def test_full_code_is_not_truncated_and_fences_survive_embedded_markdown():
    code = "```example```\n" + "x = 1\n" * 10000
    payload = chapter("<pre>" + code + "</pre>")
    index = extract(payload)
    assert len(index["entries"][0]["preview"]) <= 160
    selected = extract(payload, [index["entries"][0]["id"]])
    assert selected["entries"][0]["code"] == code.rstrip("\n")
    assert "````\n```example```" in markdown(selected)


@pytest.mark.parametrize("payload", [[], {}, {"html": 1, "url": URL}])
def test_invalid_payload_is_usage_error(payload):
    with pytest.raises(UsageError):
        extract(payload)


def test_extract_cli_uses_no_auth_browser_or_network(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("local extraction must not access auth or the network")

    monkeypatch.setattr("orly.commands.load_cookie", forbidden)
    monkeypatch.setattr("orly.commands.Answers", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(chapter("<pre>work()</pre>"))))
    monkeypatch.setattr(sys, "argv", ["orly", "extract", "-", "--json"])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "index" and result["code_blocks"] == 1


def test_extract_file_and_selected_blocks(monkeypatch, capsys, tmp_path):
    payload = chapter("<pre>first()</pre><pre>second()</pre>")
    path = tmp_path / "chapter.json"
    path.write_text(json.dumps(payload))
    index = extract(payload)
    monkeypatch.setattr(sys, "argv", ["orly", "extract", str(path), "--block", "b1", "--snapshot", index["chapter_sha256"], "--json"])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert [e["code"] for e in result["entries"]] == ["second()"]


def test_bad_json_has_structured_usage_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not JSON"))
    monkeypatch.setattr(sys, "argv", ["orly", "extract", "-", "--json"])
    assert main() == 2
    assert json.loads(capsys.readouterr().out)["error"] == "usage"


@pytest.mark.parametrize("source", [None, "false", "true"])
def test_sources_are_opt_in_for_markdown_and_json(monkeypatch, capsys, source):
    payload = chapter('<div data-type="example" id="e"><pre>work()</pre></div>')
    payload["reference"] = {"title": "A Book Title"}
    result = extract(payload)
    rendered = markdown(result, source=source == "true")
    assert ("A Book Title" in rendered) == (source == "true")
    assert (URL in rendered) == (source == "true")
    argv = ["orly", "extract", "-", "--json"]
    if source is not None:
        argv.extend(["--source", source])
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert ("url" in output) == (source == "true")
    assert ("url" in output["entries"][0]) == (source == "true")
    assert output["chapter_sha256"] == result["chapter_sha256"]
