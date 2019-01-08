import logging

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured
from django.db.models import signals

from . import settings

logger = logging.getLogger(__name__)


class ElasticAppConfig(AppConfig):

    """AppConfig for Search3."""

    name = 'elasticsearch_django'
    verbose_name = "Elasticsearch"
    configs = []

    def ready(self):
        """Validate config and connect signals."""
        super(ElasticAppConfig, self).ready()
        _validate_config(settings.get_setting('strict_validation'))
        if settings.get_setting('auto_sync'):
            _connect_signals()
        else:
            logger.debug("SEARCH_AUTO_SYNC has been disabled.")


def _validate_config(strict=False):
    """Validate settings.SEARCH_SETTINGS."""
    for index in settings.get_index_names():
        _validate_mapping(index, strict=strict)
        for model in settings.get_index_models(index):
            _validate_model(model)


def _validate_mapping(index, strict=False):
    """Check that an index mapping JSON file exists."""
    try:
        settings.get_index_mapping(index)
    except IOError:
        if strict:
            raise ImproperlyConfigured("Index '%s' has no mapping file." % index)
        else:
            logger.warning("Index '%s' has no mapping, relying on ES instead.", index)


def _validate_model(model):
    """Check that a model configured for an index subclasses the required classes."""
    if not hasattr(model, 'as_search_document'):
        raise ImproperlyConfigured(
            "'%s' must implement `as_search_document`." % model
        )
    if not hasattr(model.objects, 'get_search_queryset'):
        raise ImproperlyConfigured(
            "'%s.objects must implement `get_search_queryset`." % model
        )


def _connect_signals():
    """Connect up post_save, post_delete signals for models."""
    for index in settings.get_index_names():
        for model in settings.get_index_models(index):
            _connect_model_signals(model)


def _connect_model_signals(model):
    """Connect signals for a single model."""
    if settings.auto_sync(model):
        dispatch_uid = '%s.post_save' % model._meta.model_name
        logger.debug("Connecting search index model sync signal: %s", dispatch_uid)
        signals.post_save.connect(_on_model_save, sender=model, dispatch_uid=dispatch_uid)
        dispatch_uid = '%s.post_delete' % model._meta.model_name
        logger.debug("Connecting search index model sync signal: %s", dispatch_uid)
        signals.post_delete.connect(_on_model_delete, sender=model, dispatch_uid=dispatch_uid)
    else:
        logger.debug("Auto sync disabled for '%s', ignoring update.", model._meta.model_name)


def _on_model_save(sender, **kwargs):
    """Update document in search index post_save."""
    update_fields = kwargs['update_fields']
    instance = kwargs['instance']
    for index in instance.search_indexes:
        _update_search_index(instance=instance, index=index, update_fields=update_fields)


def _update_search_index(*, instance, index, update_fields):
    """Process index / update search index update actions."""
    try:
        if update_fields:
            instance.update_search_document(index=index, update_fields=update_fields)
        else:
            instance.index_search_document(index=index)
    except Exception:
        logger.exception("Error handling 'post_save' signal for %s", instance)


def _on_model_delete(sender, **kwargs):
    """
    Remove documents from search index post_delete.

    When deleting a document from the search index, always use force=True
    to ignore the in_search_queryset check - as by definition on a delete
    the object will no longer in exist in the database.

    """
    instance = kwargs['instance']
    for index in instance.search_indexes:
        try:
            instance.delete_search_document(index=index)
        except Exception:
            logger.exception("Error handling 'on_delete' signal for %s", instance)
