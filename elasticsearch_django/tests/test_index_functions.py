# -*- coding: utf-8 -*-
"""Search3 app index function tests."""
import mock

from django.test import TestCase

from ..index import (
    create_index,
    update_index,
    delete_index,
    prune_index,
    _prune_hit,
    scan_index,
    bulk_actions
)
from ..tests import (
    TestModel,
    TestModelManager
)


class IndexFunctionTests(TestCase):

    """Test index functions."""

    @mock.patch('elasticsearch_django.index.get_client')
    @mock.patch('elasticsearch_django.index.get_index_mapping')
    def test_create_index(self, mock_mapping, mock_client):
        """Test the create_index function."""
        mock_client.return_value = mock.Mock()
        create_index('foo')
        mock_client.assert_called_once_with()
        mock_mapping.assert_called_once_with('foo')
        mock_client.return_value.indices.create.assert_called_once_with(
            index='foo', body=mock_mapping.return_value
        )

    from django.db.models.query import QuerySet

    @mock.patch.object(QuerySet, 'iterator')
    @mock.patch('elasticsearch_django.index.get_client')
    @mock.patch('elasticsearch_django.index.bulk_actions')
    @mock.patch('elasticsearch_django.index.get_index_models')
    @mock.patch('elasticsearch.helpers.bulk')
    def test_update_index(self, mock_bulk, mock_models, mock_actions, mock_client, mock_qs):
        """Test the update_index function."""
        mock_foo = mock.Mock
        mock_foo.search_doc_type = mock.PropertyMock(return_value='bar')
        mock_foo.objects = mock.PropertyMock(return_value=mock.Mock())
        mock_models.return_value = [mock_foo]
        responses = update_index('foo')
        self.assertEqual(responses, [mock_bulk.return_value])

    @mock.patch('elasticsearch_django.index.get_client')
    def test_delete_index(self, mock_client):
        """Test the delete_index function."""
        delete_index('foo')
        mock_client.assert_called_once()
        mock_client.return_value.indices.delete.assert_called_once_with(index='foo')

    @mock.patch('elasticsearch_django.index.helpers')
    @mock.patch('elasticsearch_django.index.scan_index')
    @mock.patch('elasticsearch_django.index._prune_hit')
    @mock.patch('elasticsearch_django.index.bulk_actions')
    @mock.patch('elasticsearch_django.index.get_index_models')
    @mock.patch('elasticsearch_django.index.get_client')
    def test_prune_index(
        self, mock_client, mock_models,
        mock_actions, mock_prune, mock_scan, mock_helpers
    ):
        """Test the prune_index function."""

        # this forces one single evaluation of the outer and inner for loop
        mock_models.return_value = [TestModel]
        mock_scan.return_value = ["hit"]

        # _prune_hit returns an object, so bulk should be called
        mock_prune.return_value = TestModel()
        # should return a list with one item in it
        self.assertEqual(prune_index('foo'), [mock_helpers.bulk.return_value])
        # should have called actions and bulk once each
        mock_actions.assert_called_once()
        mock_helpers.bulk.assert_called_once()

        mock_actions.reset_mock()
        mock_helpers.bulk.reset_mock()
        # if there are no objects to prune
        mock_prune.return_value = None
        # should return an empty list
        self.assertEqual(prune_index('foo'), [])
        # shouldn't call either actions or bulk (as there's no need)
        mock_actions.assert_not_called()
        mock_helpers.bulk.assert_not_called()

    @mock.patch.object(TestModelManager, 'in_search_queryset')
    def test__prune_hit(self, mock_qs):
        """Test the _prune_hit function."""
        hit = {"_id": 1, "_index": "foo"}
        mock_qs.return_value = True
        self.assertIsNone(_prune_hit(hit, TestModel))

        mock_qs.return_value = False
        # should now return an instance of TestModel
        obj = _prune_hit(hit, TestModel)
        self.assertIsInstance(obj, TestModel)
        self.assertEqual(obj.id, hit['_id'])

    @mock.patch('elasticsearch_django.index.get_client')
    @mock.patch('elasticsearch_django.index.helpers')
    def test_scan_index(self, mock_helpers, mock_client):
        """Test the scan_index function."""
        query = {'query': {'type': {'value': 'testmodel'}}}
        # mock_helpers.scan.return_value = ['foo', 'bar']
        # cast to list to force evaluation of the generator
        response = list(scan_index('foo', TestModel))
        mock_helpers.scan.assert_called_once_with(
            mock_client.return_value,
            query=query,
            index='foo'
        )
        self.assertEqual(response, list(mock_helpers.scan.return_value))

    @mock.patch.object(TestModel, 'as_search_action')
    def test_bulk_actions(self, mock_action):
        """Test the bulk_actions function."""
        # cannot pass in in '_all' as the bulk_actions
        with self.assertRaises(AssertionError):
            list(bulk_actions([], '_all', 'index'))

        mock_action.return_value = 'foo'
        objects = [TestModel(), TestModel()]

        self.assertEqual(
            list(bulk_actions(objects, 'foo', 'update')),
            ['foo', 'foo']
        )

        # now let's add in a bad object, and check we still get the good one
        self.assertEqual(
            list(bulk_actions([TestModel(), "bad"], 'foo', 'update')),
            ['foo']
        )
