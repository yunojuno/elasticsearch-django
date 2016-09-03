# -*- coding: utf-8 -*-
"""Remove all documents in a search index that no longer exist in source queryset."""
from elasticsearch_django.management.commands import BaseSearchCommand
from elasticsearch_django.index import prune_index


class Command(BaseSearchCommand):

    """Run the management command."""

    help = "Remove all out-of-date documents in a search index."
    description = "Prune search index"

    def do_index_command(self, index, **options):
        """Prune search index."""
        return prune_index(index)
