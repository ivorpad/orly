# Python command dispatch

## Constrain valid command values

Use an `Enum` for a fixed vocabulary instead of passing arbitrary strings
through application logic. Convert an external value with the enum constructor;
unknown values raise `ValueError`. Use enum members in internal interfaces.
A type annotation communicates the contract; it does not validate an incoming
value at runtime.

Original book example, using sauces as the fixed vocabulary:

```python
from enum import Enum
class MotherSauce(Enum):
    BÉCHAMEL = "Béchamel"
    VELOUTÉ = "Velouté"
    ESPAGNOLE = "Espagnole"
    TOMATO = "Tomato"
    HOLLANDAISE = "Hollandaise"
```

```pycon
>>>MotherSauce("Hollandaise") # OKAY

>>>MotherSauce("Alabama White BBQ Sauce")
ValueError: 'Alabama White BBQ Sauce' is not a valid MotherSauce
```

Use `Literal` for a simple static restriction. Prefer `Enum` when runtime
checking, iteration, or a name-to-value mapping is required. For choices that
change at runtime, use a dictionary and explicit membership checks instead
of an enum.

## Select a callable instead of repeating branches

Map supported keys to callable handlers. Look up the handler and call it;
keep each handler responsible for its own operation. Do not derive executable
code from an input string with `eval`.

Original book example:

```pycon
>>> def f1(s): return s.upper()
>>> def f2(s): return s.lower()
>>> def f3(s): return f'{s * 4}!'

>>> key = 'loop'
>>> {'hack': f1, 'code': f2, 'loop': f3}[key]('Py')
'PyPyPyPy!'
```

This table still uses string keys. It centralizes selection but does not
constrain the command vocabulary by itself. The enum example above addresses
that separate concern. Do not treat the two excerpts as a combined application.

A command can be a function or bound method. A separate class with an
`execute()` method is not required merely to represent a callable operation.
