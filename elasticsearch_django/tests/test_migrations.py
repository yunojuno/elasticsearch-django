from django.apps import apps
from django.db import connection
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ProjectState
from django.test import TestCase


class MigrationsTests(TestCase):
    def test_for_missing_migrations(self):
        """Checks if there're models changes which aren't reflected in migrations."""
        current_models_state = ProjectState.from_apps(apps)
        # skip tracking changes for TestModel
        current_models_state.remove_model("elasticsearch_django", "testmodel")

        migrations_loader = MigrationExecutor(connection).loader
        migrations_detector = MigrationAutodetector(
            from_state=migrations_loader.project_state(), to_state=current_models_state
        )
        if migrations_detector.changes(graph=migrations_loader.graph):
            self.fail(
                "Your models have changes that are not yet reflected "
                "in a migration. You should add them now."
            )
