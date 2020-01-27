"""Delete a search index (and all documents therein)."""
from __future__ import annotations

import logging
from typing import Any

from ...index import delete_index
from . import BaseSearchCommand, CommandReturnType

logger = logging.getLogger(__name__)


class Command(BaseSearchCommand):
    """Delete search index."""

    help = "Clears out the specified (or all) search index completely."
    description = "Delete search index"

    def do_index_command(self, index: str, **options: Any) -> CommandReturnType:
        """Delete search index."""
        if options["interactive"]:
            logger.warning("This will permanently delete the index '%s'.", index)
            if not self._confirm_action():
                logger.warning(
                    "Aborting deletion of index '%s' at user's request.", index
                )
                return None
        return delete_index(index)
