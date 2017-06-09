# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.test import TestCase
from django.test.utils import override_settings

from ..compat import mock
from ..settings import (
    get_client,
    get_setting,
    get_settings,
    get_connection_string,
    get_index_config,
    get_index_names,
    get_index_models,
    get_model_indexes,
    get_document_models,
    get_document_model
)
from ..tests import TestModel


TEST_SETTINGS = {
    "connections": {
        "default": "https://foo",
        "backup": "https://bar"
    },
    "indexes": {
        "baz": {
            "models": ["elasticsearch_django.TestModel"]
        }
    },
    "settings": {
        "foo": "bar"
    }
}


class SettingsFunctionTests(TestCase):

    """Tests for the settings functions."""

    @mock.patch('elasticsearch_django.settings.get_connection_string')
    def test_get_client(self, mock_conn):
        """Test the get_client function."""
        mock_conn.return_value = "http://foo"
        client = get_client()
        self.assertEqual(len(client.transport.hosts), 1)
        self.assertEqual(client.transport.hosts[0]['host'], 'foo')

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_settings(self):
        """Test the get_settings method."""
        self.assertEqual(get_settings(), TEST_SETTINGS['settings'])

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_setting(self):
        """Test the get_setting method."""
        self.assertEqual(get_setting('foo'), 'bar')

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_connection_string(self):
        """Test the get_connection_string method."""
        self.assertEqual(get_connection_string(), TEST_SETTINGS['connections']['default'])
        self.assertEqual(get_connection_string('backup'), TEST_SETTINGS['connections']['backup'])

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_index_config(self):
        """Test the get_index_config method."""
        self.assertEqual(get_index_config('baz'), TEST_SETTINGS['indexes']['baz'])

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_index_names(self):
        """Test the get_index_names method."""
        self.assertEqual(get_index_names(), list(TEST_SETTINGS['indexes'].keys()))

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_index_models(self):
        """Test the get_index_models function."""
        from django.apps import apps
        models = get_index_models('baz')
        self.assertEqual(models, [apps.get_model('elasticsearch_django', 'TestModel')])

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_model_indexes(self):
        """Test the get_model_indexes function."""
        # TestModel is in the TEST_SETTINGS
        self.assertEqual(get_model_indexes(TestModel), ['baz'])
        # plain old object isn't in any indexes
        self.assertEqual(get_model_indexes(object), [])

    def test_get_index_mapping(self):
        """Test the get_index_mapping function."""
        # this interacts with the file system, not going to bother to test
        # as it just opens a file and loads in into a dict - there's no 'logic'
        pass

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_document_models(self):
        """Test the get_document_models function."""
        self.assertEqual(get_document_models(), {'baz.testmodel': TestModel})

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_document_model(self):
        """Test the get_document_model function."""
        self.assertEqual(get_document_model('baz', 'testmodel'), TestModel)
