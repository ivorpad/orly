# Java: Item 9, firstLineOfFile using try-with-resources

## Feedforward

Use try-with-resources for AutoCloseable resources so cleanup occurs on return and exceptions while preserving the primary failure.

## Code reference

[Effective Java, 3rd Edition · Item 9, firstLineOfFile using try-with-resources](https://learning.oreilly.com/library/view/-/9780134686097/ch2.xhtml#pch2ex38)

```java
// try-with-resources - the best way to close resources!
static String firstLineOfFile(String path) throws IOException {
    try (BufferedReader br = new BufferedReader(
           new FileReader(path))) {
       return br.readLine();
    }
}
```

Verbatim current-parser output; book callout markers and whitespace are retained.

Extracted code SHA-256: `cde1a6709153929ab5bf9c7fdaa669e879f35fa069501de9a86d7598784d62c6`.

## Feedback

- The reader closes after both successful reads and read failures.
- If reading and closing both throw, the read exception remains primary and the close exception is suppressed.

## Decision required

Should the caller propagate IOException or choose an explicit fallback?

## Evidence boundary

Rules and checks are agent synthesis from the cited example and adjacent explanation. Checks are proposed acceptance criteria; they were not executed. The excerpt is reference material, not a standalone program.
