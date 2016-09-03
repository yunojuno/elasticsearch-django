# -*- coding: utf-8 -*-
"""Update all documents in a search index."""
from elasticsearch_django.management.commands import BaseSearchCommand
from elasticsearch_django.index import update_index


class Command(BaseSearchCommand):

    """Run the management command."""

    help = "Update all documents in a search index."
    description = "Update search index."

    def do_index_command(self, index, **options):
        """Update search index."""
        return update_index(index)
