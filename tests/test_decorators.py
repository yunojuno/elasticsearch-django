from django.db.models import signals
from django.test import TestCase

from elasticsearch_django.apps import _on_model_save
from elasticsearch_django.decorators import _strip_on_model_save, disable_search_updates


class DecoratorTests(TestCase):
    def setUp(self):
        signals.post_save.connect(_on_model_save)

    def tearDown(self):
        signals.post_save.disconnect(_on_model_save)

    def test_disable_updates(self):
        """Check the decorator removes _on_model_save from signal receivers."""
        self.assertNotEqual(signals.post_save.receivers, [])
        self.assertEqual(signals.post_save.receivers[0][1](), _on_model_save)
        with disable_search_updates():
            self.assertEqual(signals.post_save.receivers, [])
        self.assertEqual(signals.post_save.receivers[0][1](), _on_model_save)

    def test__strip_on_model_save(self):
        self.assertNotEqual(signals.post_save.receivers, [])
        self.assertEqual(_strip_on_model_save(), [])
