# -*- coding: utf-8 -*-
"""Create a search index."""
import logging

from elasticsearch.exceptions import TransportError

from . import BaseSearchCommand
from ...index import (
    delete_index,
    create_index,
    update_index
)

logger = logging.getLogger(__name__)


class Command(BaseSearchCommand):

    """Run the management command."""

    help = "Delete, create and update a new search index using the relevant mapping file."
    description = "Rebuild search index"

    def do_index_command(self, index, **options):
        """Rebuild search index."""
        if options['interactive']:
            logger.warn("This will permanently delete the index '%s'.", index)
            if not self._confirm_action():
                logger.warn("Aborting rebuild of index '%s' at user's request.", index)
                return

        try:
            delete = delete_index(index)
        except TransportError:
            logger.info("Index %s does not exist, cannot be deleted.", index)
        create = create_index(index)
        update = update_index(index)

        return {
            'delete': delete,
            'create': create,
            'update': update
        }
