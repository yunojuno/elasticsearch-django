from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured

import elasticsearch_django
from elasticsearch_django.apps import (
    ElasticAppConfig,
    _connect_signals,
    _delete_from_search_index,
    _on_model_delete,
    _on_model_save,
    _update_search_index,
    _validate_config,
    _validate_mapping,
    _validate_model,
)
from elasticsearch_django.models import SearchDocumentMixin

from .models import ExampleModel


class SearchAppsConfigTests:
    """Tests for the apps module ready function."""

    @mock.patch("elasticsearch_django.apps.settings.get_setting", lambda x: False)
    @mock.patch("elasticsearch_django.apps._validate_config")
    @mock.patch("elasticsearch_django.apps._connect_signals")
    def test_ready(self, mock_signals, mock_config):
        """Test the AppConfig.ready method."""
        # mock_setting = True
        config = ElasticAppConfig("foo_bar", elasticsearch_django)
        config.ready()
        mock_config.assert_called_once_with(False)
        mock_signals.assert_called_once_with()


class SearchAppsValidationTests:
    """Tests for the apps module validation functions."""

    def test__validate_model(self):
        """Test _validate_model function."""
        # 1. model doesn't implement as_search_document
        with mock.patch("tests.models.ExampleModel") as tm:
            del tm.as_search_document
            with pytest.raises(ImproperlyConfigured):
                _validate_model(tm)

        # 2. model.objects doesn't implement get_search_queryset
        with mock.patch("tests.models.ExampleModel") as tm:
            del tm.objects.get_search_queryset
            with pytest.raises(ImproperlyConfigured):
                _validate_model(tm)

        # model should pass
        with mock.patch("tests.models.ExampleModel") as tm:
            _validate_model(tm)

    @mock.patch("elasticsearch_django.apps.settings")
    def test__validate_mapping(self, mock_settings):
        """Test _validate_model function."""
        _validate_mapping("foo", strict=True)
        mock_settings.get_index_mapping.assert_called_once_with("foo")
        mock_settings.get_index_mapping.side_effect = IOError()
        with pytest.raises(ImproperlyConfigured):
            _validate_mapping("foo", strict=True)
        # shouldn't raise error
        _validate_mapping("foo", strict=False)

    @mock.patch("elasticsearch_django.apps.settings")
    @mock.patch("elasticsearch_django.apps._validate_model")
    @mock.patch("elasticsearch_django.apps._validate_mapping")
    def test__validate_config(self, mock_mapping, mock_model, mock_settings):
        """Test _validate_model function."""
        mock_settings.get_index_names.return_value = ["foo"]
        mock_settings.get_setting.return_value = "full"
        mock_settings.get_index_models.return_value = [ExampleModel]
        _validate_config()
        mock_mapping.assert_called_once_with("foo", strict=False)
        mock_model.assert_called_once_with(ExampleModel)

    @mock.patch("elasticsearch_django.apps.settings")
    @mock.patch("elasticsearch_django.apps._validate_model")
    @mock.patch("elasticsearch_django.apps._validate_mapping")
    def test__validate_config_invalid_strategy(
        self, mock_mapping, mock_model, mock_settings
    ):
        """Test _validate_model function with an invalid update_strategy."""
        mock_settings.get_index_names.return_value = ["foo"]
        mock_settings.get_setting.return_value = "foo"
        mock_settings.get_index_models.return_value = [ExampleModel]
        with pytest.raises(ImproperlyConfigured):
            _validate_config()

    @mock.patch("elasticsearch_django.apps.signals")
    @mock.patch("elasticsearch_django.apps.settings")
    def test__connect_signals(self, mock_settings, mock_signals):
        """Test the _connect_signals function."""
        # this should connect up the signals once, for ExampleModel
        mock_settings.get_index_names.return_value = ["foo"]
        mock_settings.get_index_models.return_value = [ExampleModel]
        _connect_signals()
        mock_signals.post_save.connect.assert_called_once_with(
            _on_model_save, sender=ExampleModel, dispatch_uid="examplemodel.post_save"
        )
        mock_signals.post_delete.connect.assert_called_once_with(
            _on_model_delete,
            sender=ExampleModel,
            dispatch_uid="examplemodel.post_delete",
        )

    @mock.patch("elasticsearch_django.apps._delete_from_search_index")
    def test__on_model_delete(self, mock_delete):
        """Test the _on_model_delete function."""
        obj = mock.Mock(spec=SearchDocumentMixin, search_indexes=["foo", "bar"])
        _on_model_delete(None, instance=obj)
        assert mock_delete.call_count == 2
        mock_delete.assert_called_with(instance=obj, index="bar")

    @mock.patch("elasticsearch_django.apps.settings.auto_sync")
    @mock.patch("elasticsearch_django.apps.pre_delete")
    def test__delete_from_search_index_True(self, mock_delete_signal, mock_auto_sync):
        """Test the _delete_from_search_index function when AUTO_SYNC=True."""
        mock_auto_sync.return_value = True
        obj = mock.Mock(spec=SearchDocumentMixin)
        _delete_from_search_index(instance=obj, index="foo")
        mock_delete_signal.send.assert_called_once_with(
            sender=obj.__class__, instance=obj, index="foo"
        )
        obj.delete_search_document.assert_called_once_with(index="foo")

    @mock.patch("elasticsearch_django.apps.settings.auto_sync")
    @mock.patch("elasticsearch_django.apps.pre_delete")
    def test__delete_from_search_index_False(self, mock_delete_signal, mock_auto_sync):
        """Test the _delete_from_search_index function when AUTO_SYNC=False."""
        obj = mock.Mock(spec=SearchDocumentMixin)
        mock_auto_sync.return_value = False
        _delete_from_search_index(instance=obj, index="foo")
        mock_delete_signal.send.assert_called_once_with(
            sender=obj.__class__, instance=obj, index="foo"
        )
        obj.delete_search_document.assert_not_called()

    @mock.patch("elasticsearch_django.apps._update_search_index")
    def test__on_model_save__index(self, mock_update):
        """Test the _on_model_save function without update_fields."""
        obj = mock.Mock(spec=SearchDocumentMixin, search_indexes=["foo"])
        _on_model_save(None, instance=obj, update_fields=None)
        mock_update.assert_called_once_with(
            instance=obj, index="foo", update_fields=None
        )

    @mock.patch("elasticsearch_django.apps._update_search_index")
    def test__on_model_save__update(self, mock_update):
        """Test the _on_model_save function without update_fields."""
        obj = mock.Mock(spec=SearchDocumentMixin, search_indexes=["foo"])
        _on_model_save(None, instance=obj, update_fields=["bar"])
        mock_update.assert_called_once_with(
            instance=obj, index="foo", update_fields=["bar"]
        )

    @mock.patch("elasticsearch_django.apps._in_search_queryset")
    @mock.patch("elasticsearch_django.apps.settings.auto_sync")
    def test__update_search_index__auto_sync(self, mock_auto_sync, mock_in_qs):
        """Test the _update_search_index function with an index action."""
        mock_auto_sync.return_value = True
        mock_in_qs.return_value = False
        obj = mock.Mock(spec=SearchDocumentMixin)
        _update_search_index(instance=obj, index="foo", update_fields=None)
        assert obj.index_search_document.call_count == 0
        assert obj.update_search_document.call_count == 0
        obj.index_search_document.assert_not_called()
        obj.update_search_document.assert_not_called()
        obj.delete_search_document.assert_not_called()

    @mock.patch("elasticsearch_django.apps._in_search_queryset")
    @mock.patch("elasticsearch_django.apps.settings.auto_sync")
    def test__update_search_index__not_in_qs(self, mock_auto_sync, mock_in_qs):
        """Test the _update_search_index function with an index action."""
        mock_auto_sync.return_value = True
        mock_in_qs.return_value = True
        obj = mock.Mock(spec=SearchDocumentMixin)
        _update_search_index(instance=obj, index="foo", update_fields=None)
        assert obj.index_search_document.call_count == 1
        assert obj.update_search_document.call_count == 0
        obj.index_search_document.assert_called_once_with(index="foo")
        obj.update_search_document.assert_not_called()
        obj.delete_search_document.assert_not_called()

    @mock.patch("elasticsearch_django.apps._in_search_queryset")
    @mock.patch("elasticsearch_django.apps.settings.auto_sync")
    def test__update_search_index__no_auto_sync(self, mock_auto_sync, mock_in_qs):
        """Test the _update_search_index function with an index action."""
        mock_auto_sync.return_value = False
        mock_in_qs.return_value = True
        obj = mock.Mock(spec=SearchDocumentMixin)
        _update_search_index(instance=obj, index="foo", update_fields=None)
        assert obj.index_search_document.call_count == 0
        assert obj.update_search_document.call_count == 0
        obj.index_search_document.assert_not_called()
        obj.update_search_document.assert_not_called()
        obj.delete_search_document.assert_not_called()
