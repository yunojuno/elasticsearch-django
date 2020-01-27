"""Create a search index."""
from __future__ import annotations

from typing import Any

from ...index import create_index
from . import BaseSearchCommand, CommandReturnType


class Command(BaseSearchCommand):
    """Run the management command."""

    help = "Create a new search index using the relevant mapping file."
    description = "Create search index"

    def do_index_command(self, index: str, **options: Any) -> CommandReturnType:
        """Create new search index."""
        return create_index(index)
