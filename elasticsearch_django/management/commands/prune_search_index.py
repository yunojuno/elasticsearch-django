"""Remove all documents in a search index that no longer exist in source queryset."""
from __future__ import annotations

from typing import Any

from ...index import prune_index
from . import BaseSearchCommand, CommandReturnType


class Command(BaseSearchCommand):
    """Run the management command."""

    help = "Remove all out-of-date documents in a search index."
    description = "Prune search index"

    def do_index_command(self, index: str, **options: Any) -> CommandReturnType:
        """Prune search index."""
        return prune_index(index)
