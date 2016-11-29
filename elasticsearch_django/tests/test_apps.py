# -*- coding: utf-8 -*-
import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from ..apps import (
    ElasticAppConfig,
    _validate_config,
    _validate_model,
    _validate_mapping,
    _connect_signals,
    _on_model_delete,
    _on_model_save,
    _update_search_index,
)
from ..models import SearchDocumentMixin
from ..tests import TestModel
from .. import tests


class SearchAppsConfigTests(TestCase):

    """Tests for the apps module ready function."""

    @mock.patch('elasticsearch_django.apps.settings.get_setting')
    @mock.patch('elasticsearch_django.apps._validate_config')
    @mock.patch('elasticsearch_django.apps._connect_signals')
    def test_ready(self, mock_signals, mock_config, mock_setting):
        """Test the AppConfig.ready method."""
        mock_setting.return_value = True  # auto-sync
        config = ElasticAppConfig('foo_bar', tests)
        config.ready()
        mock_config.assert_called_once_with(mock_setting.return_value)
        mock_signals.assert_called_once_with()

        mock_setting.return_value = False  # auto-sync
        mock_signals.reset_mock()
        mock_config.reset_mock()
        config.ready()
        mock_config.assert_called_once_with(mock_setting.return_value)
        mock_signals.assert_not_called()


class SearchAppsValidationTests(TestCase):

    """Tests for the apps module validation functions."""

    def test__validate_model(self):
        """Test _validate_model function."""
        # 1. model doesn't implement as_search_document
        with mock.patch('elasticsearch_django.tests.test_apps.TestModel') as tm:
            del tm.as_search_document
            self.assertRaises(ImproperlyConfigured, _validate_model, tm)

        # 2. model.objects doesn't implement get_search_queryset
        with mock.patch('elasticsearch_django.tests.test_apps.TestModel') as tm:
            del tm.objects.get_search_queryset
            self.assertRaises(ImproperlyConfigured, _validate_model, tm)

        # model should pass
        with mock.patch('elasticsearch_django.tests.test_apps.TestModel') as tm:
            _validate_model(tm)

    @mock.patch('elasticsearch_django.apps.settings')
    def test__validate_mapping(self, mock_settings):
        """Test _validate_model function."""
        _validate_mapping('foo', strict=True)
        mock_settings.get_index_mapping.assert_called_once_with('foo')
        mock_settings.get_index_mapping.side_effect = IOError()
        self.assertRaises(ImproperlyConfigured, _validate_mapping, 'foo', strict=True)
        # shouldn't raise error
        _validate_mapping('foo', strict=False)

    @mock.patch('elasticsearch_django.apps.settings')
    @mock.patch('elasticsearch_django.apps._validate_model')
    @mock.patch('elasticsearch_django.apps._validate_mapping')
    def test__validate_config(self, mock_mapping, mock_model, mock_settings):
        """Test _validate_model function."""
        mock_settings.get_index_names.return_value = ['foo']
        mock_settings.get_index_models.return_value = [TestModel]
        _validate_config()
        mock_mapping.assert_called_once_with('foo', strict=False)
        mock_model.assert_called_once_with(TestModel)

    @mock.patch('elasticsearch_django.apps.signals')
    @mock.patch('elasticsearch_django.apps.settings')
    def test__connect_signals(self, mock_settings, mock_signals):
        """Test the _connect_signals function."""
        # this should connect up the signals once, for TestModel
        mock_settings.get_index_names.return_value = ['foo']
        mock_settings.get_index_models.return_value = [TestModel]
        _connect_signals()
        mock_signals.post_save.connect.assert_called_once_with(
            _on_model_save,
            sender=TestModel,
            dispatch_uid='testmodel.post_save'
        )
        mock_signals.post_delete.connect.assert_called_once_with(
            _on_model_delete,
            sender=TestModel,
            dispatch_uid='testmodel.post_delete'
        )

    @mock.patch('elasticsearch_django.apps._update_search_index')
    def test__on_model_delete(self, mock_update):
        """Test the _on_model_delete function."""
        obj = SearchDocumentMixin()
        _on_model_delete(None, instance=obj)
        mock_update.assert_called_once_with(obj, 'delete')

    @mock.patch('elasticsearch_django.apps._update_search_index')
    def test__on_model_save(self, mock_update):
        """Test the _on_model_save function."""
        obj = SearchDocumentMixin()
        _on_model_save(None, instance=obj)
        mock_update.assert_called_once_with(obj, 'index')

    @mock.patch('elasticsearch_django.apps.logger')
    @mock.patch('elasticsearch_django.settings.get_model_indexes')
    @mock.patch.object(SearchDocumentMixin, 'update_search_index')
    def test__update_search_index(self, mock_update, mock_indexes, mock_logger):
        """Test the _update_search_index function."""
        mock_indexes.return_value = ['foo']
        obj = SearchDocumentMixin()
        _update_search_index(obj, 'delete')
        mock_update.assert_called_once_with('delete', index='foo')

        # if the update bombs, should still pass, and call logger
        mock_update.reset_mock()
        mock_update.side_effect = Exception()
        _update_search_index(obj, 'delete')
        mock_update.assert_called_once_with('delete', index='foo')
        mock_logger.exception.assert_called_once()

        # check that it calls for each configured index
        mock_update.reset_mock()
        mock_indexes.return_value = ['foo', 'bar']
        obj = SearchDocumentMixin()
        _update_search_index(obj, 'delete')
        mock_update.assert_has_calls([
            mock.call('delete', index='foo'),
            mock.call('delete', index='bar')
        ])

        # confirm that it is **not** called if auto_sync is off
        mock_update.reset_mock()
        with mock.patch('elasticsearch_django.settings.get_setting') as mock_settings:
            mock_settings.return_value = False
            _update_search_index(obj, 'delete')
            mock_update.assert_not_called()
