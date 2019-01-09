from unittest import mock

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
from .. import tests
from ..models import SearchDocumentMixin
from ..tests import TestModel


class SearchAppsConfigTests(TestCase):

    """Tests for the apps module ready function."""

    @mock.patch('elasticsearch_django.apps.settings.get_setting')
    @mock.patch('elasticsearch_django.apps.settings.get_settings')
    @mock.patch('elasticsearch_django.apps._validate_config')
    @mock.patch('elasticsearch_django.apps._connect_signals')
    def test_ready(self, mock_signals, mock_config, mock_settings, mock_setting):
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

    @mock.patch.object(SearchDocumentMixin, 'search_indexes', ['foo'])
    @mock.patch.object(SearchDocumentMixin, 'delete_search_document')
    def test__on_model_delete(self, mock_delete):
        """Test the _on_model_delete function."""
        obj = SearchDocumentMixin()
        _on_model_delete(None, instance=obj)
        mock_delete.assert_called_once_with(index='foo')

    @mock.patch.object(SearchDocumentMixin, 'search_indexes', ['foo', 'bar'])
    @mock.patch.object(SearchDocumentMixin, 'delete_search_document')
    def test__on_model_delete__multiple_indexes(self, mock_delete):
        """Test the _on_model_delete function with multiple indexes."""
        obj = SearchDocumentMixin()
        _on_model_delete(None, instance=obj)
        self.assertEqual(mock_delete.call_count, 2)

    @mock.patch('elasticsearch_django.apps._update_search_index')
    def test__on_model_save__index(self, mock_update):
        """Test the _on_model_save function without update_fields."""
        obj = mock.Mock(spec=SearchDocumentMixin, search_indexes=['foo'])
        _on_model_save(None, instance=obj, update_fields=None)
        mock_update.assert_called_once_with(instance=obj, index='foo', update_fields=None)

    @mock.patch('elasticsearch_django.apps._update_search_index')
    def test__on_model_save__update(self, mock_update):
        """Test the _on_model_save function without update_fields."""
        obj = mock.Mock(spec=SearchDocumentMixin, search_indexes=['foo'])
        _on_model_save(None, instance=obj, update_fields=['bar'])
        mock_update.assert_called_once_with(instance=obj, index='foo', update_fields=['bar'])

    def test__update_search_index(self):
        """Test the _update_search_index function with an index action."""
        obj = mock.Mock(spec=SearchDocumentMixin)
        _update_search_index(instance=obj, index='foo', update_fields=None)
        self.assertEqual(obj.index_search_document.call_count, 1)
        self.assertEqual(obj.update_search_document.call_count, 0)

    def test__update_search_update(self):
        """Test the _update_search_index function with an update action."""
        obj = mock.Mock(spec=SearchDocumentMixin)
        _update_search_index(instance=obj, index='foo', update_fields=['bar'])
        self.assertEqual(obj.update_search_document.call_count, 1)
        self.assertEqual(obj.index_search_document.call_count, 0)
