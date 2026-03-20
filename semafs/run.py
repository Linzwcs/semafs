"""Backward-compatible module entrypoint.

Supports legacy invocations like:
`python -m semafs.run ...`
"""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
