# JavaScript: Snippet 2.38: Error handling

## Feedforward

Await the asynchronous work inside try and handle rejection in catch; rejected awaited promises throw into that handler.

## Code reference

[Advanced JavaScript · Snippet 2.38: Error handling](https://learning.oreilly.com/library/view/-/9781789800104/C11078_2_Final_EPUB_SW.xhtml#_idParaDest-91)

```javascript
async function tryCatchExample() {
  // Try to do asynchronous work
  try{
    const value1 = await Promise.resolve( 'Success 1' );
    const value2 = await Promise.resolve( 'Success 2' );
    const value3 = await Promise.reject( 'Oh no!' );
  } 
  
  // Catch errors
  catch( err ){
    console.log( err ); // Expected output: Oh no!
  }
}
tryCatchExample()
```

Contiguous p.snippet paragraphs joined with newlines; prototype adapter, absent from the released parser.

Extracted code SHA-256: `ef5372f90c1775cf8a0617cc920851d97b8c52bdbe4b8378827ab3b50b2b3455`.

## Feedback

- The rejected third promise reaches catch with Oh no!.
- Fulfilled awaited promises proceed without entering catch.

## Decision required

Should catch recover, report, or rethrow? The book example logs the error.

## Evidence boundary

Rules and checks are agent synthesis from the cited example and adjacent explanation. Checks are proposed acceptance criteria; they were not executed. The excerpt is reference material, not a standalone program.
