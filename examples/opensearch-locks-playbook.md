# OpenSearch locks

## Concurrent document updates

Official OpenSearch guidance.

- Use optimistic concurrency control for competing edits to one document. Keep the `_seq_no` and `_primary_term` returned with the version you read; send both as `if_seq_no` and `if_primary_term` on the conditional write.
- On HTTP 409, retrieve the current document and reconsider the change before retrying. Reusing a stale replacement body with fresh revision numbers defeats the conflict check.
- Use create-only indexing when the requirement is that a document ID must not already exist. Ordinary indexing with an existing ID replaces the document.
- `refresh` controls search visibility. It does not reserve a document for a writer.

Original conditional-index example, REST:

```http
PUT sample-index/_doc/1?if_seq_no=3&if_primary_term=1
{
  "name": "Updated Example",
  "price": 39.99
}
```

## Index blocks and disk protection

Official OpenSearch guidance.

- Use a `write` block to stop data writes across an index while permitting metadata changes. Use `read_only` when metadata changes must also be blocked.
- A successful Blocks API write-block response accounts for the block on all shards and completion of in-flight writes.
- Scope the target index explicitly. An index block has no application lock owner or lease.
- When disk usage crosses the flood-stage watermark, OpenSearch applies `index.blocks.read_only_allow_delete` to affected indexes. Restore disk capacity; the automatic block is released when utilization falls below the high watermark. Clearing a setting alone does not fix the disk condition.
- Leave `search_only` management to OpenSearch.

Original Python write-block example. Assumes an initialized `client`:

```python
response = client.indices.add_block(
  block = "write",
  index = "test-index"
)
```

## Using OpenSearch as a distributed lock store

Book guidance on distributed-lock safety:

- A process can pause, lose its lease, and resume writing after another process acquires the lease. A delayed request can also arrive after ownership changes.
- For fencing, issue an increasing token on each acquisition. Send it with every protected write; the destination must reject older tokens. Establish the new token at the destination before relying on the fence.
- Conditional writes at the protected storage are another mechanism discussed in the book. Protecting only the lock record leaves writes to other resources unprotected.
- When all protected writes go to one storage service with conditional writes, a separate lock service may be redundant.

Official OpenSearch primitives:

- Create-only indexing can arbitrate creation of a document ID. That primitive alone supplies no lease renewal, expiry protocol, or fencing of another service.
- Conditional deletion can reject deletion of a document revision that has changed. It does not establish application ownership by itself.

Original Python conditional-delete example. This deletes product `3`; it is not a lock-release implementation. Assumes an initialized `client`:

```python
response = client.delete(
  id = "3",
  index = "products",
  params = { "if_seq_no": "43", "if_primary_term": "1" }
)
```

The retrieved sources do not provide a complete OpenSearch lease-lock implementation. Do not treat these snippets as one.
