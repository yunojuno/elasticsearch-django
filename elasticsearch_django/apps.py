import logging

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured
from django.db.models import signals

from . import settings
from .signals import pre_index, pre_update, pre_delete

logger = logging.getLogger(__name__)


class ElasticAppConfig(AppConfig):

    """AppConfig for Search3."""

    name = "elasticsearch_django"
    verbose_name = "Elasticsearch"
    configs = []

    def ready(self):
        """Validate config and connect signals."""
        super(ElasticAppConfig, self).ready()
        _validate_config(settings.get_setting("strict_validation"))
        _connect_signals()


def _validate_config(strict=False):
    """Validate settings.SEARCH_SETTINGS."""
    for index in settings.get_index_names():
        _validate_mapping(index, strict=strict)
        for model in settings.get_index_models(index):
            _validate_model(model)
    if settings.get_setting("update_strategy", "full") not in ["full", "partial"]:
        raise ImproperlyConfigured(
            "Invalid SEARCH_SETTINGS: 'update_strategy' value must be 'full' or 'partial'."
        )


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
    if not hasattr(model, "as_search_document"):
        raise ImproperlyConfigured("'%s' must implement `as_search_document`." % model)
    if not hasattr(model.objects, "get_search_queryset"):
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
    dispatch_uid = "%s.post_save" % model._meta.model_name
    logger.debug("Connecting search index model post_save signal: %s", dispatch_uid)
    signals.post_save.connect(_on_model_save, sender=model, dispatch_uid=dispatch_uid)
    dispatch_uid = "%s.post_delete" % model._meta.model_name
    logger.debug("Connecting search index model post_delete signal: %s", dispatch_uid)
    signals.post_delete.connect(
        _on_model_delete, sender=model, dispatch_uid=dispatch_uid
    )


def _on_model_save(sender, **kwargs):
    """Update document in search index post_save."""
    instance = kwargs.pop("instance")
    update_fields = kwargs.pop("update_fields")
    for index in instance.search_indexes:
        try:
            _update_search_index(
                instance=instance, index=index, update_fields=update_fields
            )
        except Exception:
            logger.exception("Error handling 'on_save' signal for %s", instance)


def _on_model_delete(sender, **kwargs):
    """Remove documents from search indexes post_delete."""
    instance = kwargs.pop("instance")
    for index in instance.search_indexes:
        try:
            _delete_from_search_index(instance=instance, index=index)
        except Exception:
            logger.exception("Error handling 'on_delete' signal for %s", instance)


def _in_search_queryset(*, instance, index) -> bool:
    """Wrapper around the instance manager method."""
    try:
        return instance.__class__.objects.in_search_queryset(instance.id, index=index)
    except Exception:
        logger.exception("Error checking object in_search_queryset.")
        return False


def _update_search_index(*, instance, index, update_fields):
    """Process index / update search index update actions."""
    if not _in_search_queryset(instance=instance, index=index):
        logger.debug(
            "Object (%r) is not in search queryset, ignoring update.", instance
        )
        return

    try:
        if update_fields:
            pre_update.send(
                sender=instance.__class__,
                instance=instance,
                index=index,
                update_fields=update_fields,
            )
            if settings.auto_sync(instance):
                instance.update_search_document(
                    index=index, update_fields=update_fields
                )
        else:
            pre_index.send(sender=instance.__class__, instance=instance, index=index)
            if settings.auto_sync(instance):
                instance.index_search_document(index=index)
    except Exception:
        logger.exception("Error handling 'post_save' signal for %s", instance)


def _delete_from_search_index(*, instance, index):
    """Remove a document from a search index."""
    pre_delete.send(sender=instance.__class__, instance=instance, index=index)
    if settings.auto_sync(instance):
        instance.delete_search_document(index=index)
