"""Create a search index."""
from __future__ import annotations

import logging
from typing import Any

from elasticsearch.exceptions import TransportError

from ...index import create_index, delete_index, update_index
from . import BaseSearchCommand, CommandReturnType

logger = logging.getLogger(__name__)


class Command(BaseSearchCommand):
    """Run the management command."""

    help = (
        "Delete, create and update a new search index using the relevant mapping file."
    )
    description = "Rebuild search index"

    def do_index_command(self, index: str, **options: Any) -> CommandReturnType:
        """Rebuild search index."""
        if options["interactive"]:
            logger.warning("This will permanently delete the index '%s'.", index)
            if not self._confirm_action():
                logger.warning(
                    "Aborting rebuild of index '%s' at user's request.", index
                )
                return None

        try:
            delete = delete_index(index)
        except TransportError:
            delete = {}
            logger.info("Index %s does not exist, cannot be deleted.", index)
        create = create_index(index)
        update = update_index(index)

        return {"delete": delete, "create": create, "update": update}
