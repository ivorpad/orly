# O'Reilly Answers HTTP API

Derived by instrumenting `learning.oreilly.com/answers2` in Chrome. Private and
undocumented — it can change without notice. Prefer the `orly` CLI; reach for raw HTTP
only for something the CLI doesn't expose.

Base: `https://learning.oreilly.com/api/v1/miso-answers-relay-service`

| Method | Path | Returns |
|---|---|---|
| POST | `/questions/` | `{question_id, is_finished:false, ...}` |
| GET | `/user-question-history/` | DRF page: `{count, next, previous, results[]}` |
| GET | `/user-question-history/<id>/` | the full record |

## Asking

`POST /questions/` with `Content-Type: application/json`:

```json
{
  "question": "...",
  "fq": "<entitlement + content-type filter>",
  "source_fl": ["custom_attributes.ourn", "url", "cover_image", "authors", "html", "..."],
  "related_resource_fl": ["..."],
  "cite_link": true,
  "_pipeline_config": {"snippet_length": 500, "highlight_length": 200, "version": "v3"},
  "query_source": "original",
  "question_source_page": "answers",
  "answer_render_page": "answers"
}
```

`fq` encodes the account's entitlements — which content types are searched and which
permission tiers are excluded. Copy it verbatim from `orly` (the `FQ` constant); a
wrong `fq` silently changes which books are eligible. It goes stale if the
subscription changes.

## Two behaviours that will bite you

**No streaming.** The UI looks like it streams, but `miso_response.data.answer` is `""`
until `is_finished` flips true, then arrives whole. Poll `/user-question-history/<id>/`.
Typical time to finish is 12–25s.

**A fresh question 404s for ~2s** on the history endpoint before the record lands. Treat
404 as "not ready yet", not as an error, with a ~30s grace window.

## Answer shape

`miso_response.data`:

| Field | Notes |
|---|---|
| `answer` | Markdown, with `[[^N]](url)` citation footnotes |
| `sources[]` | `title`, `child_title` (chapter), `authors[]`, `date`, `url`, `child_url` (deep link), `highlight_text` (the cited passage), `html` (full chapter markup — huge, skip it) |
| `related_questions[]` | suggested follow-ups; often empty |
| `related_resources[]` | same shape as sources |
| `finish_reason` | `"success"` on a good answer |
| `blocked_reason` | `"none"` unless refused |

## Auth

Cookie auth. Two cookies matter:

- `orm-jwt` — access JWT, ~1h `exp` claim
- `orm-rt` — refresh token

Either alone is a **401**. Sent together the gateway refreshes silently, so an expired
`orm-jwt` still works. `groot_sessionid` is *not* used by this API — sending only it is
a 401, and dropping it entirely still returns 200.

**The server re-issues both cookies on every response** with `Max-Age=2592000`. A client
that ignores `Set-Cookie` goes stale; one that persists it rolls the session forward 30
days from last use. `orly` writes the jar back after each call, atomically.

httpx gotcha: `dict(client.cookies)` raises `CookieConflict` because Akamai's `_abck`
cookie exists under several domains. Walk `client.cookies.jar` and prefer the
`oreilly.com`-scoped entry.

## Cookie extraction (macOS Chrome)

Keychain service `Chrome Safe Storage` → PBKDF2-HMAC-SHA1, salt `saltysalt`, 1003
iterations, 16-byte key → AES-128-CBC, IV = 16 spaces. Strip the `v10`/`v11` prefix and
PKCS#7 padding. Chrome ≥104 prepends a 32-byte domain hash to the plaintext — detect by
a failed UTF-8 decode and skip those bytes. Copy the DB before reading; it is locked
while Chrome runs.
