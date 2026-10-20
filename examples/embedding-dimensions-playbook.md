# Choosing embedding dimensions

- Choose embedding model and output dimensionality separately. A shortened `text-embedding-3-large` vector is not equivalent to a `text-embedding-3-small` vector of the same length.
- `text-embedding-3-large` defaults to 3,072 dimensions; `text-embedding-3-small` defaults to 1,536. The model name is not GPT-3.
- Do not choose the maximum solely because it is available. Higher dimensions cost more vector storage and distance-computation work; retain them when measured retrieval quality justifies that cost.
- Shorten only models that support it. Matryoshka training makes useful representations available in leading portions of the vector. Arbitrarily truncating another model has no equivalent guarantee.
- Use the supported `dimensions` parameter for shorter OpenAI `text-embedding-3` outputs. Keep query and document embeddings on the same model and dimensionality.
- Do not assign a dimension count solely from a domain label such as “legal,” “technical,” or “chatbot.” Verify retrieval on the actual corpus and query distribution.

## Select a size

Selection procedure synthesized from the books’ dimensionality trade-offs and retrieval-evaluation guidance:

1. Prepare representative queries with known relevant passages. Include the distinctions the application must retrieve correctly.
2. Establish a full-dimension baseline. Compare shorter outputs while keeping the corpus, chunking, retrieval depth, and search configuration comparable.
3. Measure retrieval quality with Recall@k or nDCG, alongside query latency and vector-index memory/storage. Choose k to match the passages the application consumes.
4. Select the smallest dimensionality that meets the application’s quality and operating limits. Keep full dimensions if shortening loses retrieval quality the application needs.

For `text-embedding-3-large`, 768, 1,536, and 3,072 provide a quarter/half/full comparison. These are experimental candidates, not mandated sizes or guaranteed quality levels. Set the acceptable quality loss from application requirements, not an assumed universal percentage.

## Original Python example

This book example obtains the default small-model embedding and prints its actual length. It does not demonstrate dimension selection or a shortened output.

```python
import os
from openai import OpenAI

client = OpenAI()

text_to_embed = "Data strategy is the key to powerful AI."

EMBEDDING_MODEL = "text-embedding-3-small"

response = client.embeddings.create(
    input=text_to_embed,
    model=EMBEDDING_MODEL
)

embedding = response.data[0].embedding

print(f"Original Text: {text_to_embed}")
print(f"Embedding Vector (first 5 dimensions): {embedding[:5]}...")
print(f"Total dimensions: {len(embedding)}")
```

The default small-model result is 1,536 dimensions. Printing the first five values does not shorten the stored `embedding` variable.

## Cost distinction

Raw vector storage scales with dimensionality at a fixed numeric representation. Halving dimensions halves those raw vector bytes; total index memory and query latency need not halve.

Official OpenAI documentation clarification: embedding API usage is charged by input tokens. Reducing output dimensions mainly saves downstream storage and search resources; it does not itself reduce the model’s per-token API price.
