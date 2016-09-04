# -*- coding: utf-8 -*-
"""Access to SEARCH_SETTINGS Django conf.

The SEARCH_SETTINGS dict in the Django conf contains three
major blocks - 'connections', 'indexes' and 'settings'.

This module contains helper functions to extract information
from the settings, as well as validation of settings.

"""
import json
import os

from django.apps import apps
from django.conf import settings

from elasticsearch import Elasticsearch


def get_client(connection='default'):
    """Return configured elasticsearch client."""
    return Elasticsearch(get_connection_string(connection))


def get_settings():
    """Return settings from Django conf."""
    return settings.SEARCH_SETTINGS['settings']


def get_setting(key):
    """Return specific search setting from Django conf."""
    return get_settings()[key]


def get_connection_string(connection='default'):
    """Return index settings from Django conf."""
    return settings.SEARCH_SETTINGS['connections'][connection]


def get_index_config(index):
    """Return index settings from Django conf."""
    return settings.SEARCH_SETTINGS['indexes'][index]


def get_index_names():
    """Return list of the names of all configured indexes."""
    return settings.SEARCH_SETTINGS['indexes'].keys()


def get_index_mapping(index):
    """Return the JSON mapping file for an index.

    Mappings are stored as JSON files in the mappings subdirectory of this
    app. They must be saved as {{index}}.json.

    Args:
        index: string, the name of the index to look for.

    """
    # app_path = apps.get_app_config('elasticsearch_django').path
    mappings_dir = get_setting('mappings_dir')
    filename = '%s.json' % index
    path = os.path.join(mappings_dir, filename)
    with open(path, 'r') as f:
        return json.load(f)


def get_index_models(index):
    """Return list of models configured for a named index.

    Args:
        index: string, the name of the index to look up.

    """
    models = []
    for app_model in get_index_config(index).get('models'):
        app, model = app_model.split('.')
        models.append(apps.get_model(app, model))
    return models


def get_model_indexes(model):
    """Return list of all indexes in which a model is configured.

    A model may be configured to appear in multiple indexes. This function
    will return the names of the indexes as a list of strings. This is
    useful if you want to know which indexes need updating when a model
    is saved.

    Args:
        model: a Django model class.

    """
    indexes = []
    for index in get_index_names():
        for app_model in get_index_models(index):
            if app_model == model:
                indexes.append(index)
    return indexes


def get_document_models():
    """Return dict of index.doc_type: model."""
    mappings = {}
    for i in get_index_names():
        for m in get_index_models(i):
            key = '%s.%s' % (i, m._meta.model_name)
            mappings[key] = m
    return mappings


def get_document_model(index, doc_type):
    """Return dict of index.doc_type: model."""
    return get_document_models().get('%s.%s' % (index, doc_type))
