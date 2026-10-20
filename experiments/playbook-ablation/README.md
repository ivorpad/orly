# Playbook extraction ablation

Run date: 2026-10-20. CLI under test: v0.2.1, commit `f78615a`.

**One Markdown contract is feasible. The current extraction path is insufficient.**
Manual selection recovered a relevant code reference for all five books, with
one additional HTML adapter. None of the automatic variants succeeded across
the five cases. This tests evidence extraction, not whether a coding agent can
implement the resulting playbook correctly.

## Results

Success means the output includes a whole code block that addresses the task,
as judged against manually reviewed example labels. Returning unrelated code
does not count. All four chapter variants use a 12-block limit.

| Language and actual book | Chapter start, mixed | Chapter start, code | Citation end, code | Citation end, mixed | Curated reference |
|---|---:|---:|---:|---:|---|
| Python · Fluent Python, 2nd Edition | No | Yes | No | No | [Example 18-3](playbooks/python.md) |
| Rust · Programming Rust, 2nd Edition | No | Yes | Match failed | Match failed | [Propagating Errors](playbooks/rust.md) |
| Go · 100 Go Mistakes and How to Avoid Them | No | No | Yes | Yes | [Mistake #35](playbooks/go.md) |
| Java · Effective Java, 3rd Edition | No | No | Empty | No code | [Item 9](playbooks/java.md) |
| JavaScript · Advanced JavaScript | No | Empty | Empty | No code | [Snippet 2.38](playbooks/javascript.md), adapter required |
| Relevant-code coverage | **0/5** | **2/5** | **1/5** | **1/5** | **5/5, manually curated** |

The citation-only baseline did not supply the relevant examples. The Rust
excerpt did contain a fenced legacy `try!` statement, so citation-only output
is not universally code-free; it did not provide the requested `?` example.

The curated column is an upper bound after human inspection, not a fifth
automatic competitor. Its JavaScript recovery uses a prototype adapter absent
from the released CLI. The playbook rules and feedback checks are synthesis;
the code is extracted from the book. No source example was executed.

## What failed

- **Selection direction.** Python's citation follows the relevant exception
  handling example. Starting after it returns decorators, CSV rewriting, and
  even Scheme examples instead. Java's citation is Item 9's closing paragraph,
  after all its examples, so the code variant returns an empty success.
- **Chapter-wide prefix limits.** Go's relevant helper is block 232; Java's
  try-with-resources example is block 224. Selecting the first 12 code blocks
  spends the budget on earlier topics. Increasing the limit is a workaround,
  not relevance selection.
- **Markup coverage.** Advanced JavaScript has 314 `p.snippet` paragraphs and
  no `<pre>` or `<code>` elements. Grouping consecutive snippet paragraphs
  and attaching the following caption recovers Snippet 2.38 exactly, including
  indentation. The current parser classifies these lines as ordinary prose.
- **Reference identity.** Original IDs exist as example-container IDs,
  section IDs, descendant line anchors, preceding code-image anchors, and
  section headings. The released parser does not expose these as code identity.
  The experiment validates each curated fragment against the cached source DOM;
  some links identify a section rather than one exact listing. Example labels
  and code hashes disambiguate them.
- **Callouts and executable text.** Python callout numbers become bare numbers
  inside the extracted code. Go's circled callout numbers remain in the code,
  while their explanations are separate paragraphs and disappear in code-only
  output. Java preserves nonbreaking indentation spaces. These are reading
  references, not directly pasteable source. Preserve a faithful reference and
  label any cleaned adaptation separately.
- **Citation alignment.** Rust's elided excerpt does not match, even though the
  target example exists in the chapter. This is a grounding failure that needs
  an explicit fallback, not another identical request.
- **HTTP negotiation.** Four books required changing the chapter request's
  `Accept: text/html` to `Accept: */*`; each then returned HTML accepted by the
  existing client. There were five 406 responses, including the initial Rust
  probe before recovery was added. A single hardcoded media type is another
  obstacle to broad book coverage.

## Retrieval and rate handling

Five questions were submitted, sequentially. The requested Learning Go title
returned a catalog-only citation, so its concrete alternate, 100 Go Mistakes,
became the Go case. The requested JavaScript: The Definitive Guide title was
not retrieved; Advanced JavaScript became the JavaScript case. No extra search
was used to hide those retrieval failures. Three of five originally requested
titles were used; the final cohort still contains five books and five languages.

The runner enforces at least five seconds between request starts, including
polls and chapter reads, with no concurrent requests. It honors numeric or
date-form Retry-After for 429s and uses bounded retries for GET only. It never
automatically resubmits a rate-limited question. These paths were not exercised
by a 429 during this run.

The source acquisition used **31 HTTP requests: 5 question submissions and
26 GETs**, including answer polling and media-type recovery. **No 429 responses
occurred.** All extraction variants and the curated recovery ran offline on
the same cached HTML. No Chrome or Keychain access was used.

## Command implications

Use a shared pipeline with small markup adapters:

1. Require a concrete chapter citation; distinguish catalog-only results.
2. Cache one source fetch and negotiate supported HTML media types.
3. Normalize code containers, captions, callouts, and reference IDs.
4. Retrieve a relevant section around the citation, including preceding code.
5. Select task-relevant examples; do not assume the nearest later code applies.
6. Render a Markdown rule, code reference, proposed checks, decisions, and gaps.

Keep raw code, callout annotations, and cleaned code separate. Return an
explicit evidence gap for missing code or mismatched citations. A successful
HTTP response with zero examples must not masquerade as a grounded playbook.

Do not ship a generic playbook command by simply combining `read --code` and
`--from-citation`. The five Markdown playbooks show the desired output shape;
the experiment does not establish an automatic selector's accuracy.

## Reproduction and limits

```bash
# Acquires missing sources only; preserves question IDs to avoid duplicate asks.
uv run python experiments/playbook-ablation/run.py

# Offline scoring and Markdown generation after acquisition.
uv run python experiments/playbook-ablation/analyze.py
```

[results.json](results.json) contains source identities, chapter hashes,
variant counts, relevance labels, and curated code links/hashes. Full answer
records, HTML, variant outputs, and request telemetry stay in the ignored
`.agent/playbook-ablation/` cache. No authentication values are included.

The four chapter variants form a 2×2 comparison of citation-end anchoring and
code-only filtering, with a fixed block limit. A three-code-block pilot was
run first; the table reports the fixed-12 rerun on the same cached sources.
Equal block limits do not mean equal characters or tokens: a code block can
be much larger than a prose block. This is not a fixed-token-budget test.

There is one retrieval per language, no repeated model sampling, and no
blinded assessment. Relevance labels were assigned after inspecting the
examples. The sample spans four publisher markup families but only five
books. It supports concrete failure cases and implementation requirements,
not a population-wide success rate or coding-agent effectiveness claim.
