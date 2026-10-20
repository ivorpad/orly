"""Chapter retrieval, selection, references, and CLI error contracts."""

import json
import sys

import httpx
import pytest

from orly.api import Answers, NotFound, UsageError
from orly.auth import AuthError
from orly.chapter import chapter_text, select_chapter
from orly.cli import main

URL = 'https://learning.oreilly.com/library/view/-/9781492056348/ch15.html'
HTML = '''<html><body><h1>TypedDict</h1>
<p>See <a href="ch05.html#classes">Chapter 5</a>.</p>
<p>First item.</p><p>Second item. Let’s explore this behavior.</p>
<div data-type="example"><h5>Example 15-5. Using a <code>BookDict</code></h5>
<pre>&gt;&gt;&gt; x = 1  <a class="co" href="#note1"><img alt="1"></a>
&gt;&gt;&gt; print(x)
1</pre></div>
<dl class="calloutlist"><dt><a id="note1" class="co"><img alt="1"></a></dt>
<dd><p>Read <a href="ch05.html#records">records</a> for details.</p></dd></dl>
<p>Following explanation.</p><pre>second_example()</pre></body></html>'''


def payload(html=HTML):
    return {'url': URL, 'isbn': '9781492056348', 'file': 'ch15.html', 'html': html,
            'reference': {'title': 'Fluent Python', 'chapter': '15. Type Hints',
                          'authors': ['Luciano Ramalho']}}


def select(**kwargs):
    return select_chapter(payload(), code=False, start=None, limit=12, **kwargs)


def test_code_includes_caption_callouts_and_book_references():
    result = select_chapter(payload(), code=True, start='Let’s explore this behavior.', limit=1)
    block, = result['blocks']
    assert block['caption'] == 'Example 15-5. Using a BookDict'
    assert block['text'] == '>>> x = 1  1\n>>> print(x)\n1'
    assert block['annotations'][0]['label'] == '1'
    assert block['annotations'][0]['references'][0]['url'].endswith('/ch05.html#records')
    text = chapter_text(result)
    assert 'Fluent Python' in text and 'Luciano Ramalho' in text
    assert '1. Read records for details.' in text
    assert result['remaining_blocks'] == 1


def test_prose_keeps_code_notes_and_text_links_without_duplicate_notes():
    result = select()
    text = chapter_text(result)
    assert 'See Chapter 5.' in text
    assert '/ch05.html#classes' in text
    assert '>>> print(x)' in text
    assert text.count('Read records for details.') == 1
    assert text.count('Example 15-5. Using a BookDict') == 1
    assert '1. Read records' in text
    assert all('html' not in b for b in result['blocks'])


def test_citation_matching_tolerates_inserted_bullets():
    result = select_chapter(payload(), code=True, start='Search excerpt inserts - First item. Second item. Let’s explore this behavior.', limit=1, citation=True)
    assert result['blocks'][0]['text'].startswith('>>> x')


def test_missing_anchor_is_explicit():
    with pytest.raises(NotFound):
        select_chapter(payload(), code=True, start='not in this chapter', limit=1)


def test_large_code_is_whole_and_not_truncated():
    code = '    x = 1\n' * 15000
    result = select_chapter(payload('<pre>' + code + '</pre><pre>other()</pre>'), code=True, start=None, limit=1)
    assert result['blocks'][0]['text'] == code.rstrip('\n')
    assert result['remaining_blocks'] == 1


def client(handler):
    api = Answers('orm-jwt=test; orm-rt=test', persist=False)
    api.http.close()
    api.http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return api


def test_endpoint_nested_path_and_full_html():
    seen = []
    def handler(req):
        assert req.headers["Accept"] == "*/*"
        seen.append(str(req.url))
        return httpx.Response(200, text=HTML, headers={'content-type': 'text/html'})
    api = client(handler)
    out = api.chapter(URL.replace('ch15.html', 'OEBPS/Text/ch15.xhtml') + '?ourn=x#anchor')
    assert out['html'] == HTML
    assert seen == ['https://learning.oreilly.com/api/v2/epubs/urn:orm:book:9781492056348/files/OEBPS/Text/ch15.xhtml']


@pytest.mark.parametrize('url', ['http://learning.oreilly.com/library/view/-/isbn/x.html',
    'https://evil.example/library/view/-/isbn/x.html', '//evil.example/x',
    'https://learning.oreilly.com/library/view/-/isbn/',
    'https://learning.oreilly.com/library/view/-/isbn/../x.html'])
def test_invalid_url_never_sends_request(url):
    def handler(req):
        pytest.fail('invalid URL sent a request')
    with pytest.raises(UsageError):
        client(handler).chapter(url)


@pytest.mark.parametrize('target', ['https://evil.example/x', 'http://learning.oreilly.com/x', '//evil.example/x'])
def test_redirect_cannot_send_cookies_off_host(target):
    seen = []
    def handler(req):
        seen.append(req.url)
        return httpx.Response(302, headers={'location': target})
    with pytest.raises(RuntimeError, match='refusing chapter redirect'):
        client(handler).chapter(URL)
    assert len(seen) == 1


def test_same_host_redirect_is_allowed():
    seen = []
    def handler(req):
        seen.append(req.url)
        if len(seen) == 1:
            return httpx.Response(302, headers={'location': '/chapter-file.html'})
        return httpx.Response(200, text=HTML, headers={'content-type': 'application/xhtml+xml'})
    assert client(handler).chapter(URL)['html'] == HTML
    assert len(seen) == 2


@pytest.mark.parametrize('status,exception', [(404, NotFound), (401, AuthError), (403, AuthError)])
def test_chapter_errors_are_typed(status, exception):
    with pytest.raises(exception):
        client(lambda req: httpx.Response(status)).chapter(URL)


def test_non_html_is_rejected():
    with pytest.raises(RuntimeError, match='did not return HTML'):
        client(lambda req: httpx.Response(200, json={'detail': 'no chapter'})).chapter(URL)


@pytest.fixture
def fake_api(monkeypatch):
    class Fake:
        def __init__(self, cookie): pass
        def history(self, n):
            return [{'question_id': '42daa7c4-' + 'x' * 27}]
        def get(self, qid):
            return {'question_id': qid, 'is_finished': True, 'miso_response': {'data': {
                'sources': [{'title': 'Fluent Python', 'authors': ['Luciano Ramalho'],
                             'child_url': URL, 'highlight_text': 'Let’s explore this behavior.'}]}}}
        def chapter(self, url):
            assert url == URL
            return payload()
    monkeypatch.setattr('orly.commands.Answers', Fake)
    monkeypatch.setattr('orly.commands.load_cookie', lambda: 'test')


def run(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, 'argv', ['orly', 'read', *args, '--json'])
    status = main()
    return status, json.loads(capsys.readouterr().out)


def test_read_answer_json(fake_api, monkeypatch, capsys):
    status, result = run(monkeypatch, capsys, '42daa7c4', '1', '--code', '--from-citation', '--limit', '1')
    assert status == 0 and len(result['blocks']) == 1
    assert result['reference']['source'] == 1
    assert 'html' not in result


def test_read_url_raw(fake_api, monkeypatch, capsys):
    status, result = run(monkeypatch, capsys, URL, '--raw')
    assert status == 0 and result['html'] == HTML


@pytest.mark.parametrize('args,code,kind', [
    (['42daa7c4'], 2, 'usage'), (['42daa7c4', '0'], 2, 'usage'),
    (['42daa7c4', '2'], 3, 'not_found'),
    ([URL, '--from-citation'], 2, 'usage'),
    ([URL, '--limit', '0'], 2, 'usage'),
    ([URL, '--raw', '--code'], 2, 'usage'),
    ([URL, '--start', 'absent'], 3, 'not_found')])
def test_json_errors(fake_api, monkeypatch, capsys, args, code, kind):
    status, result = run(monkeypatch, capsys, *args)
    assert status == result['exit_code'] == code
    assert result['error'] == kind
