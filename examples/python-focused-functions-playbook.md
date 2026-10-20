# Focused Python functions

- Give each function one specific, unified purpose. Describe it in one sentence.
  If the description combines unrelated jobs, split them into separate functions.
- Keep orchestration focused on sequencing named steps. Put each step's
  implementation in its own function so the caller exposes the workflow.
- Pass inputs as arguments and return results. Avoid communicating through
  globals or directly changing another module's variables.
- Keep pure transformations free of I/O and hidden state. For the same inputs,
  return the same result without changing the caller's objects.
- Mutate arguments only when the caller expects it. Object methods may update
  their object's state; the problem is unexpected side effects.
- Split long or deeply nested functions when they hide separate tasks. A short
  function is useful when its name explains an operation and hides its details.
- Apply purity pragmatically. Do not require the whole application to be purely
  functional.

## Separate orchestration from implementation

This original book example is an illustrative workflow. The helper functions
and `Report` are intentionally not implemented in the listing.

```python
# data.science.example.py
def do_report(data_source):
    # fetch and prepare data
    data = fetch_data(data_source)
    parsed_data = parse_data(data)
    filtered_data = filter_data(parsed_data)
    polished_data = polish_data(filtered_data)
    # run algorithms on data
    final_data = analyse(polished_data)
    # create and return report
    report = Report(final_data)
    return report
```

## Name a focused transformation

This original book example gives matrix multiplication a name instead of
embedding its implementation at the call site.

```python
# matrix.multiplication.func.py
def matrix_mul(a, b):
    return [
        [sum(i * j for i, j in zip(r, c)) for c in zip(*b)]
        for r in a
    ]
a = [[1, 2], [3, 4]]
b = [[5, 1], [2, 1]]
c = matrix_mul(a, b)
```
