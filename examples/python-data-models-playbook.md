# Python data models

## TypedDict

Use `TypedDict` to describe a dictionary's keys and value types to a type checker.
It does not validate values at runtime. Annotating `json.loads()` output as a
`TypedDict` does not make the decoded data valid.

```python
from typing import TypedDict

class BookDict(TypedDict):
    isbn: str
    title: str
    authors: list[str]
    pagecount: int
```

## Dataclasses

Use a standard-library dataclass for structured object state and generated
methods. Type annotations do not validate constructor arguments. Use
`field(default_factory=...)` for mutable defaults so instances do not share them.

```python
from dataclasses import dataclass, field

@dataclass
class ClubMember:
    name: str
    guests: list[str] = field(default_factory=list)
```

## Pydantic

Use Pydantic to parse and validate values at runtime. Its ordinary fields can
coerce inputs; use strict fields when the original input type matters.
Pydantic can also decorate dataclasses.

```python
from pydantic.dataclasses import dataclass
from pydantic import StrictInt
@dataclass
class Model:
    value: StrictInt
```

`Model(value=123)` accepts the integer. `Model(value="0023")` raises a validation
error instead of converting the string.

Use `Annotated[T, Field(...)]` to attach validation constraints to a type.
Pydantic enforces those constraints at runtime; `Annotated` alone does not
validate values. Apply string length limits with `min_length` and `max_length`,
and numeric bounds with `ge` and `le`.

```python
from typing import Annotated
from pydantic import BaseModel, Field

class ModelRequest(BaseModel):
    prompt: Annotated[str, Field(min_length=1, max_length=10000)]
```

The same pattern works in Pydantic dataclasses.

```python
from typing import Annotated
from pydantic import Field
from pydantic.dataclasses import dataclass

@dataclass
class Result2:
    success: bool
    exit_code: Annotated[int, Field(ge=0)]
    duration: float
```
