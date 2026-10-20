# Go: Mistake #35, readFiles/readFile helper solution

## Feedforward

Put per-file work in a helper so defer file.Close() runs on each iteration's helper return; check os.Open before registering cleanup.

## Code reference

[100 Go Mistakes and How to Avoid Them · Mistake #35, readFiles/readFile helper solution](https://learning.oreilly.com/library/view/-/9781617299599/OEBPS/Text/04.htm#pgfId-1145048)

```go
func readFiles(ch <-chan string) error {
    for path := range ch {
        if err := readFile(path); err != nil {    ❶
            return err
        }
    }
    return nil
}
 
func readFile(path string) error {
    file, err := os.Open(path)
    if err != nil {
        return err
    }
 
    defer file.Close()                            ❷
 
    // Do something with file
    return nil
}
```

Verbatim current-parser output; book callout markers and whitespace are retained.

Extracted code SHA-256: `1a64ba326b30070a8f5b26fc7dc4ce5f56d1f5b25dd7de617dde18d9cc36f658`.

## Feedback

- Each completed iteration closes its file before the next one proceeds.
- An open failure returns its error without using a nil file.

## Decision required

How should file.Close errors be handled? This excerpt explicitly defers that topic to mistake #54.

## Evidence boundary

Rules and checks are agent synthesis from the cited example and adjacent explanation. Checks are proposed acceptance criteria; they were not executed. The excerpt is reference material, not a standalone program.

Book callout numerals appear inside the excerpt. Keep them as annotations when adapting the code; this fenced reference is not directly pasteable source.
