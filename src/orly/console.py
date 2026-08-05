"""Shared rich consoles.

`soft_wrap` when piped so URLs and quotes survive redirection into a file or
another process intact; rich would otherwise hard-wrap them at 80 columns.
"""

from __future__ import annotations

import sys

from rich.console import Console

PIPED = not sys.stdout.isatty()
console = Console(soft_wrap=PIPED)
err = Console(stderr=True)
