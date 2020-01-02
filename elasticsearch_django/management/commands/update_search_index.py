"""Update all documents in a search index."""
from ...index import update_index
from . import BaseSearchCommand


class Command(BaseSearchCommand):
    """Run the management command."""

    help = "Update all documents in a search index."
    description = "Update search index."

    def do_index_command(self, index, **options):
        """Update search index."""
        return update_index(index)
