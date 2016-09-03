# -*- coding: utf-8 -*-
"""Create a search index."""
from elasticsearch_django.management.commands import BaseSearchCommand
from elasticsearch_django.index import create_index


class Command(BaseSearchCommand):

    """Run the management command."""

    help = "Create a new search index using the relevant mapping file."
    description = "Create search index"

    def do_index_command(self, index, **options):
        """Create new search index."""
        return create_index(index)
