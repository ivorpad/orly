# OpenSearch index and alias naming

## Naming rules from books

- Give applications a stable alias. Put the physical index version behind it, so rebuilding or replacing an index does not require changing the application’s target name.
- Keep the version in the physical name. The book’s example uses alias `tweets` with physical index `tweets_v1`, then switches the alias to a newer version.
- Separate search and indexing aliases when their targets need to differ. The book uses `tweets_search` and `tweets_index`: searches can cover old and new indexes while new documents go to the new index.
- Use dates in physical index names for time-based data and retention. The OpenSearch book uses `logs-2024.07.13`. This is a time-series pattern, not a requirement for every application index.
- Keep a predictable common prefix where indexes should share template handling. Match it with an index template, such as the book’s `logs-*`, so new matching indexes receive their settings and mappings at creation.

Examples actually used in the books:

| Purpose | Alias | Physical index |
| --- | --- | --- |
| Stable application target | `tweets` | `tweets_v1` |
| Search target | `tweets_search` | `tweets_1`, later also `tweets_2` |
| Indexing target | `tweets_index` | `tweets_1`, later `tweets_2` |
| Stable forum target | `baking` | `forums`, later `baking_v1` |

## Original book examples

These are Elasticsearch book listings. They are preserved as source examples, not rewritten into Python or presented as OpenSearch book code.

Create separate search and indexing aliases for an existing index:

```http
PUT /tweets_1/_alias/tweets_search 
PUT /tweets_1/_alias/tweets_index 
```

Move an existing alias to a dedicated index in one atomic request:

```http
POST /_aliases
{
  "actions": [
    { "remove": { "alias": "baking", "index": "forums"    }},
    { "add":    { "alias": "baking", "index": "baking_v1" }}
  ]
}
```

The second listing switches the alias only. It assumes the destination index and its data are ready; it does not copy documents or synchronize concurrent writes.

Mechanical cleanup: removed numbered callout markers from the first listing.

## OpenSearch compatibility checks

Official OpenSearch documentation confirms stable aliases, atomic alias changes, and the distinction between aliases and physical indexes. An alias spanning multiple indexes needs one designated write index for indexing requests. The book’s indexing alias instead points to one index at a time.

## Enterprise convention gap

The inspected passages do not prescribe a company-wide ordering of organization, domain, environment, tenant, and dataset tokens. They also do not mandate `-read`/`-write` suffixes. Those would be organization conventions, not rules extracted from these books.
