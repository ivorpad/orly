# Rust: Propagating Errors, move_all

## Feedforward

Return Result and use ? at fallible operations to propagate recoverable errors to the caller.

## Code reference

[Programming Rust, 2nd Edition · Propagating Errors, move_all](https://learning.oreilly.com/library/view/-/9781492052586/ch07.html#propagating-errors)

```rust
use std::fs;
use std::io;
use std::path::Path;

fn move_all(src: &Path, dst: &Path) -> io::Result<()> {
    for entry_result in src.read_dir()? {  // opening dir could fail
        let entry = entry_result?;         // reading dir could fail
        let dst_file = dst.join(entry.file_name());
        fs::rename(entry.path(), dst_file)?;  // renaming could fail
    }
    Ok(())  // phew!
}
```

Verbatim current-parser output; book callout markers and whitespace are retained.

Extracted code SHA-256: `d9ee5b9c255c69199729d237ba229fdb7ecdf92825f3fb4002faf4749325718b`.

## Feedback

- Directory-open, directory-entry, and rename errors return Err.
- The success path returns Ok(()).

## Decision required

Where should the caller handle and report the propagated error?

## Evidence boundary

Rules and checks are agent synthesis from the cited example and adjacent explanation. Checks are proposed acceptance criteria; they were not executed. The excerpt is reference material, not a standalone program.
