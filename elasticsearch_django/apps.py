from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model, signals

from . import settings
from .signals import pre_delete, pre_index, pre_update

if TYPE_CHECKING:
    from elasticsearch_django.models import SearchDocumentMixin

logger = logging.getLogger(__name__)


class ElasticAppConfig(AppConfig):
    """AppConfig for Search3."""

    name = "elasticsearch_django"
    verbose_name = "Elasticsearch"
    default_auto_field = "django.db.models.AutoField"

    def ready(self) -> None:
        """Validate config and connect signals."""
        super(ElasticAppConfig, self).ready()
        _validate_config(bool(settings.get_setting("strict_validation")))
        _connect_signals()


def _validate_config(strict: bool = False) -> None:
    """Validate settings.SEARCH_SETTINGS."""
    for index in settings.get_index_names():
        _validate_mapping(index, strict=strict)
        for model in settings.get_index_models(index):
            _validate_model(model)
    if settings.get_setting("update_strategy", "full") not in ["full", "partial"]:
        raise ImproperlyConfigured(
            "Invalid SEARCH_SETTINGS: 'update_strategy' value must be "
            "'full' or 'partial'."
        )


def _validate_mapping(index: str, strict: bool = False) -> None:
    """Check that an index mapping JSON file exists."""
    try:
        settings.get_index_mapping(index)
    except IOError:
        if strict:
            raise ImproperlyConfigured("Index '%s' has no mapping file." % index)
        else:
            logger.warning("Index '%s' has no mapping, relying on ES instead.", index)


def _validate_model(model: Model) -> None:
    """Check that a model configured for an index subclasses the required classes."""
    if not hasattr(model, "as_search_document"):
        raise ImproperlyConfigured("'%s' must implement `as_search_document`." % model)
    if not hasattr(model.objects, "get_search_queryset"):
        raise ImproperlyConfigured(
            "'%s.objects must implement `get_search_queryset`." % model
        )


def _connect_signals() -> None:
    """Connect up post_save, post_delete signals for models."""
    for index in settings.get_index_names():
        for model in settings.get_index_models(index):
            _connect_model_signals(model)


def _connect_model_signals(model: type[Model]) -> None:
    """Connect signals for a single model."""
    dispatch_uid = "%s.post_save" % model._meta.model_name
    logger.debug("Connecting search index model post_save signal: %s", dispatch_uid)
    signals.post_save.connect(_on_model_save, sender=model, dispatch_uid=dispatch_uid)
    dispatch_uid = "%s.post_delete" % model._meta.model_name
    logger.debug("Connecting search index model post_delete signal: %s", dispatch_uid)
    signals.post_delete.connect(
        _on_model_delete, sender=model, dispatch_uid=dispatch_uid
    )


def _on_model_save(sender: type[Model], **kwargs: Any) -> None:
    """Update document in search index post_save."""
    instance = kwargs.pop("instance")
    update_fields = kwargs.pop("update_fields")
    for index in instance.search_indexes:
        try:
            _update_search_index(
                instance=instance, index=index, update_fields=update_fields
            )
        except Exception:  # noqa: B902
            logger.exception("Error handling 'on_save' signal for %s", instance)


def _on_model_delete(sender: type[Model], **kwargs: Any) -> None:
    """Remove documents from search indexes post_delete."""
    instance = kwargs.pop("instance")
    for index in instance.search_indexes:
        try:
            _delete_from_search_index(instance=instance, index=index)
        except Exception:  # noqa: B902
            logger.exception("Error handling 'on_delete' signal for %s", instance)


def _in_search_queryset(*, instance: Model, index: str) -> bool:
    """Return True if instance is in the index queryset."""
    try:
        return instance.__class__.objects.in_search_queryset(instance.pk, index=index)
    except Exception:  # noqa: B902
        logger.exception("Error checking object in_search_queryset.")
        return False


def _update_search_index(
    *, instance: SearchDocumentMixin, index: str, update_fields: list[str]
) -> None:
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
    except Exception:  # noqa: B902
        logger.exception("Error handling 'post_save' signal for %s", instance)


def _delete_from_search_index(*, instance: SearchDocumentMixin, index: str) -> None:
    """Remove a document from a search index."""
    pre_delete.send(sender=instance.__class__, instance=instance, index=index)
    if settings.auto_sync(instance):
        instance.delete_search_document(index=index)
