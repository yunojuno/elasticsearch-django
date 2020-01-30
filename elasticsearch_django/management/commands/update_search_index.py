"""Update all documents in a search index."""
from __future__ import annotations

from typing import Any

from ...index import update_index
from . import BaseSearchCommand, CommandReturnType


class Command(BaseSearchCommand):
    """Run the management command."""

    help = "Update all documents in a search index."
    description = "Update search index."

    def do_index_command(self, index: str, **options: Any) -> CommandReturnType:
        """Update search index."""
        return update_index(index)
