# Python: Example 18-3, mirror.py

## Feedforward

Restore the original resource state in __exit__; return a truthy value only for an exception intentionally handled.

## Code reference

[Fluent Python, 2nd Edition · Example 18-3, mirror.py](https://learning.oreilly.com/library/view/-/9781492056348/ch18.html#looking_glass_ex)

```python
import sys

class LookingGlass:

    def __enter__(self):  1
        self.original_write = sys.stdout.write  2
        sys.stdout.write = self.reverse_write  3
        return 'JABBERWOCKY'  4

    def reverse_write(self, text):  5
        self.original_write(text[::-1])

    def __exit__(self, exc_type, exc_value, traceback):  6
        sys.stdout.write = self.original_write  7
        if exc_type is ZeroDivisionError:  8
            print('Please DO NOT divide by zero!')
            return True  9
        10
```

Verbatim current-parser output; book callout markers and whitespace are retained.

Extracted code SHA-256: `40f982c5f1d25b5ca347158cd259b36a2f4c49fda1531f015bcaf6cd2c395061`.

## Feedback

- Normal completion restores sys.stdout.write.
- A ZeroDivisionError is handled by this example; another exception propagates after restoration.

## Decision required

Which exception types, if any, should the application suppress?

## Evidence boundary

Rules and checks are agent synthesis from the cited example and adjacent explanation. Checks are proposed acceptance criteria; they were not executed. The excerpt is reference material, not a standalone program.

Book callout numerals appear inside the excerpt. Keep them as annotations when adapting the code; this fenced reference is not directly pasteable source.
