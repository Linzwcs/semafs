"""Placer implementations — routing strategies for new content."""


class HintPlacer:
    """Use hint path directly, fallback to 'root'."""

    async def place(self, content: str, hint: str | None) -> str:
        """Return hint if provided, otherwise 'root'."""
        return hint if hint else "root"
