# -*- coding: utf-8 -*-
from django.test import TestCase

from ..settings import get_setting
from ..utils import disable_search_updates


class UtilsTests(TestCase):

    """elasticsearch_django.utils tests."""

    def test_disable_updates(self):

        self.assertTrue(get_setting('auto_sync'))

        with disable_search_updates():
            self.assertFalse(get_setting('auto_sync'))

        self.assertTrue(get_setting('auto_sync'))
