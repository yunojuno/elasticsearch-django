from unittest import mock

import pytest
from django.apps import apps
from django.test.utils import override_settings

from elasticsearch_django.settings import (
    auto_sync,
    get_client,
    get_connection_string,
    get_document_models,
    get_index_config,
    get_index_models,
    get_index_names,
    get_model_indexes,
    get_setting,
    get_settings,
)

from .models import ExampleModel

TEST_SETTINGS = {
    "connections": {"default": "https://foo", "backup": "https://bar"},
    "indexes": {"baz": {"models": ["tests.ExampleModel"]}},
    "settings": {"foo": "bar", "auto_sync": True, "never_auto_sync": []},
}


class SettingsFunctionTests:
    """Tests for the settings functions."""

    @mock.patch("elasticsearch_django.settings.get_connection_string")
    def test_get_client(self, mock_conn):
        """Test the get_client function."""
        mock_conn.return_value = "http://foo"
        client = get_client()
        assert len(client.transport.hosts) == 1
        assert client.transport.hosts[0]["host"] == "foo"

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_settings(self):
        """Test the get_settings method."""
        assert get_settings() == TEST_SETTINGS["settings"]

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_setting(self):
        """Test the get_setting method."""
        assert get_setting("foo") == "bar"

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_setting_with_default(self):
        """Test the get_setting method."""
        with pytest.raises(KeyError):
            get_setting("bar")
        assert get_setting("bar", "baz") == "baz"

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_connection_string(self):
        """Test the get_connection_string method."""
        assert get_connection_string() == TEST_SETTINGS["connections"]["default"]
        assert get_connection_string("backup") == TEST_SETTINGS["connections"]["backup"]

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_index_config(self):
        """Test the get_index_config method."""
        assert get_index_config("baz") == TEST_SETTINGS["indexes"]["baz"]

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_index_names(self):
        """Test the get_index_names method."""
        assert get_index_names() == list(TEST_SETTINGS["indexes"].keys())

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_index_models(self):
        """Test the get_index_models function."""
        models = get_index_models("baz")
        assert models == [apps.get_model("tests", "ExampleModel")]

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_model_indexes(self):
        """Test the get_model_indexes function."""
        # ExampleModel is in the TEST_SETTINGS
        assert get_model_indexes(ExampleModel) == ["baz"]
        # plain old object isn't in any indexes
        assert get_model_indexes(object) == []

    def test_get_index_mapping(self):
        """Test the get_index_mapping function."""
        # this interacts with the file system, not going to bother to test
        # as it just opens a file and loads in into a dict - there's no 'logic'
        pass

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_get_document_models(self):
        """Test the get_document_models function."""
        assert get_document_models() == {"baz.examplemodel": ExampleModel}

    @override_settings(SEARCH_SETTINGS=TEST_SETTINGS)
    def test_auto_sync(self):
        """Test the auto_sync function."""
        obj = ExampleModel()
        assert auto_sync(obj) is True
        # Check that if the auto_sync is False, the function also returns false.
        TEST_SETTINGS["settings"]["auto_sync"] = False
        assert auto_sync(obj) is False
        TEST_SETTINGS["settings"]["auto_sync"] = True
        assert auto_sync(obj) is True
        # Check that if a model is in never_auto_sync, then auto_sync returns false
        TEST_SETTINGS["settings"]["never_auto_sync"].append("tests.examplemodel")
        assert auto_sync(obj) is False
