"""
Access to SEARCH_SETTINGS Django conf.

The SEARCH_SETTINGS dict in the Django conf contains three
major blocks - 'connections', 'indexes' and 'settings'.

This module contains helper functions to extract information
from the settings, as well as validation of settings.

"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Union

from django.apps import apps
from django.conf import settings
from django.db.models import Model
from elasticsearch import Elasticsearch

SettingType = Union[list, dict, int, str, bool]
SettingsType = Dict[str, SettingType]


def get_client(connection: str = "default") -> Elasticsearch:
    """Return configured elasticsearch client."""
    return Elasticsearch(get_connection_string(connection))


def get_settings() -> SettingsType:
    """Return settings from Django conf."""
    return settings.SEARCH_SETTINGS["settings"]


def get_setting(key, *default: str | int | bool | list | dict) -> SettingType:
    """Return specific search setting from Django conf."""
    if default:
        return get_settings().get(key, default[0])
    else:
        return get_settings()[key]


def set_setting(key: str, value: SettingType) -> None:
    """Set specific search setting in Django conf settings."""
    get_settings()[key] = value


def get_connection_string(connection: str = "default") -> str:
    """Return index settings from Django conf."""
    return settings.SEARCH_SETTINGS["connections"][connection]


def get_index_config(index: str) -> dict[str, list[str]]:
    """Return index settings from Django conf."""
    return settings.SEARCH_SETTINGS["indexes"][index]


def get_index_names() -> list[str]:
    """Return list of the names of all configured indexes."""
    return list(settings.SEARCH_SETTINGS["indexes"].keys())


def get_index_mapping(index: str) -> dict:
    """
    Return the JSON mapping file for an index.

    Mappings are stored as JSON files in the mappings subdirectory of this
    app. They must be saved as {{index}}.json.

    Args:
        index: string, the name of the index to look for.

    """
    # app_path = apps.get_app_config('elasticsearch_django').path
    mappings_dir = get_setting("mappings_dir")
    filename = "%s.json" % index
    path = os.path.join(mappings_dir, filename)
    with open(path, "r") as f:
        return json.load(f)


def get_model_index_properties(instance: Model, index: str) -> list[str]:
    """Return the list of properties specified for a model in an index."""
    mapping = get_index_mapping(index)
    return list(mapping["mappings"]["properties"].keys())


def get_index_models(index: str) -> list[Model]:
    """Return list of models configured for a named index."""
    models = []  # type: List[Model]
    for app_model in get_index_config(index).get("models"):
        app, model = app_model.split(".")
        models.append(apps.get_model(app, model))
    return models


def get_model_indexes(model: Model) -> list[str]:
    """
    Return list of all indexes in which a model is configured.

    A model may be configured to appear in multiple indexes. This function
    will return the names of the indexes as a list of strings. This is
    useful if you want to know which indexes need updating when a model
    is saved.

    Args:
        model: a Django model class.

    """
    indexes = []  # type: List[str]
    for index in get_index_names():
        for app_model in get_index_models(index):
            if app_model == model:
                indexes.append(index)
    return indexes


def get_document_models() -> dict[str, Model]:
    """Return dict of index.doc_type: model."""
    mappings: dict[str, Model] = {}
    for i in get_index_names():
        for m in get_index_models(i):
            mappings[f"{i}.{m._meta.model_name}"] = m
    return mappings


def get_document_model(index: str, doc_type: str) -> Model | None:
    """Return model for a given index.doc_type combination."""
    raise DeprecationWarning("Mapping types have been removed from ES7.x")


def auto_sync(instance: Model) -> bool:
    """Return True if auto_sync is on for the model (instance)."""
    # this allows us to turn off sync temporarily - e.g. when doing bulk updates
    if not get_setting("auto_sync"):
        return False
    model_name = f"{instance._meta.app_label}.{instance._meta.model_name}"
    if model_name in get_setting("never_auto_sync", *[]):
        return False
    return True
