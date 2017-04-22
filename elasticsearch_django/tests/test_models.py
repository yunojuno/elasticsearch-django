# -*- coding: utf-8 -*-
import datetime
import decimal

from django.db.models import Model
from django.test import TestCase
from django.utils.timezone import now as tz_now

from elasticsearch_dsl.search import Search

from ..compat import mock
from ..models import (
    SearchDocumentMixin,
    SearchDocumentManagerMixin,
    SearchQuery,
)
from ..tests import (
    TestModel,
    TestModelManager,
    SEARCH_DOC,
)


class SearchDocumentMixinTests(TestCase):

    """Tests for the SearchDocumentMixin."""

    @mock.patch('elasticsearch_django.models.get_model_indexes')
    def test_search_indexes(self, mock_indexes):
        """Test the search_indexes function."""
        mock_indexes.return_value = 'foo'
        obj = TestModel()
        self.assertEqual(obj.search_indexes, 'foo')
        mock_indexes.assert_called_once_with(TestModel)

    def test_as_search_document(self):
        """Test the as_search_document method."""
        obj = SearchDocumentMixin()
        self.assertRaises(NotImplementedError, obj.as_search_document)

    def test_as_search_action(self):
        """Test the as_search_action method."""
        obj = TestModel()
        self.assertEqual(
            obj.as_search_action(index='foo', action='index'),
            {
                '_index': 'foo',
                '_type': 'testmodel',
                '_op_type': 'index',
                '_id': None,
                '_source': SEARCH_DOC
            }
        )

        self.assertEqual(
            obj.as_search_action(index='foo', action='update'),
            {
                '_index': 'foo',
                '_type': 'testmodel',
                '_op_type': 'update',
                '_id': None,
                'doc': SEARCH_DOC
            }
        )

        self.assertEqual(
            obj.as_search_action(index='foo', action='delete'),
            {
                '_index': 'foo',
                '_type': 'testmodel',
                '_op_type': 'delete',
                '_id': None
            }
        )

    @mock.patch('elasticsearch_django.models.get_client')
    def test_fetch_search_document(self, mock_client):
        """Test the fetch_search_document method."""
        obj = TestModel()
        # obj has no id
        self.assertRaises(AssertionError, obj.fetch_search_document, index='foo')

        # should now call the ES get method
        obj.id = 1
        response = obj.fetch_search_document(index='foo')
        mock_get = mock_client.return_value.get
        mock_get.assert_called_once_with(
            index='foo',
            doc_type=obj._meta.model_name,
            id=obj.id
        )
        self.assertEqual(response, mock_get.return_value)

    @mock.patch('elasticsearch_django.tests.TestModel.objects')
    @mock.patch.object(TestModel, 'search_indexes', new_callable=mock.PropertyMock)
    @mock.patch.object(TestModel, '_do_search_action')
    def test_update_search_index(self, mock_do_search, mock_indexes, mock_manager):
        """Test the update_search_index method."""
        obj = TestModel()

        # invalid action 'foo'
        self.assertRaises(AssertionError, obj.update_search_index, action='foo')
        mock_manager.assert_not_called()

        # valid action, but no id
        self.assertRaises(AssertionError, obj.update_search_index, action='index')
        mock_manager.assert_not_called()

        obj.id = 1
        # the object is not in the search queryset, should **not** call the update
        mock_manager.in_search_queryset.return_value = False
        response = obj.update_search_index(action='index')
        mock_manager.in_search_queryset.assert_called_once_with(obj.id, index='_all')
        self.assertIsNone(response)

        # check that 'update' actions are converted to 'index'
        mock_manager.reset_mock()
        mock_manager.in_search_queryset.return_value = True
        response = obj.update_search_index(action='update', index='foo')
        mock_manager.in_search_queryset.assert_called_once_with(obj.id, index='foo')
        mock_do_search.assert_called_once_with('foo', 'index', force=False)

        # check that 'index' actions go through as 'index'
        mock_manager.reset_mock()
        mock_do_search.reset_mock()
        response = obj.update_search_index(action='index', index='bar')
        mock_manager.in_search_queryset.assert_called_once_with(obj.id, index='bar')
        mock_do_search.assert_called_once_with('bar', 'index', force=False)

        mock_manager.reset_mock()
        mock_do_search.reset_mock()
        mock_indexes.return_value = ['foo', 'bar']
        response = obj.update_search_index(action='index')
        mock_manager.in_search_queryset.assert_called_once_with(obj.id, index='_all')
        mock_do_search.assert_has_calls([
            mock.call('foo', 'index', force=False),
            mock.call('bar', 'index', force=False)
        ])

    @mock.patch('elasticsearch_django.models.cache')
    @mock.patch('elasticsearch_django.models.get_client')
    def test__do_search_action(self, mock_client, mock_cache):
        """Test the _do_search_action method."""
        obj = TestModel()

        # valid action, but not id
        self.assertRaises(AssertionError, obj._do_search_action, index='foo', action='index')
        # id is good, but invalid action
        obj.id = 1
        self.assertRaises(AssertionError, obj._do_search_action, index='foo', action='foobar')

        obj._do_search_action(index='foo', action='index')
        mock_index = mock_client.return_value.index
        mock_index.assert_called_once_with(
            index='foo',
            doc_type=obj._meta.model_name,
            body=SEARCH_DOC,
            id=obj.id
        )

        obj._do_search_action(index='foo', action='delete')
        mock_delete = mock_client.return_value.delete
        mock_delete.assert_called_once_with(
            index='foo',
            doc_type=obj._meta.model_name,
            id=obj.id
        )

        # test the caching - cahce hit, index should not be called
        mock_client.reset_mock()
        mock_index.reset_mock()
        mock_cache.get.return_value = obj.as_search_document('foo')
        obj._do_search_action(index='foo', action='index')
        mock_index.assert_not_called()

        # cache hit, but with force=True - should call the index
        mock_client.reset_mock()
        mock_index.reset_mock()
        obj._do_search_action(index='foo', action='index', force=True)
        mock_index.assert_called_once_with(
            index='foo',
            doc_type=obj._meta.model_name,
            body=SEARCH_DOC,
            id=obj.id
        )


class SearchDocumentManagerMixinTests(TestCase):

    """Tests for the SearchDocumentManagerMixin."""

    def test_get_search_queryset(self):
        """Test the get_search_queryset method."""
        obj = SearchDocumentManagerMixin()
        self.assertRaises(NotImplementedError, obj.get_search_queryset)

    @mock.patch.object(TestModelManager, 'get_search_queryset')
    def test_in_search_queryset(self, mock_qs):
        """Test the in_search_queryset method."""
        obj = TestModel(id=1)
        TestModel.objects.in_search_queryset(obj.id)
        mock_qs.assert_called_once_with(index='_all')
        mock_qs.return_value.filter.assert_called_once_with(id=1)
        mock_qs.return_value.filter.return_value.exists.assert_called_once_with()

    def test__raw_sql(self):
        """Test the _raw_sql method."""
        self.assertEqual(
            TestModel.objects._raw_sql(((1, 2), (3, 4))),
            'SELECT CASE elasticsearch_django_testmodel."id" WHEN 1 THEN 2 WHEN 3 THEN 4 ELSE 0 END'
        )

    @mock.patch('django.db.models.query.QuerySet')
    def test_from_search_query(self, mock_qs):
        """Test the from_search_query method."""
        sq = SearchQuery(hits=[{'id': 1, 'score': 1}, {'id': 2, 'score': 2}])
        qs = TestModel.objects.from_search_query(sq)
        self.assertEqual(
            str(qs.query),
            'SELECT "elasticsearch_django_testmodel"."id", '
            '(SELECT CASE elasticsearch_django_testmodel."id" WHEN 1 THEN 1 WHEN 2 THEN 2 ELSE 0 END) '  # noqa
            'AS "search_score", (SELECT CASE elasticsearch_django_testmodel."id" WHEN 1 THEN 0 WHEN 2 '  # noqa
            'THEN 1 ELSE 0 END) AS "search_rank" FROM "elasticsearch_django_testmodel" WHERE '
            '"elasticsearch_django_testmodel"."id" IN (1, 2) ORDER BY "search_rank" ASC'
        )


class SearchQueryTests(TestCase):

    """Tests for the SearchQuery model."""

    hits = [
        {'id': 1, 'doc_type': 'foo'},
        {'id': 2, 'doc_type': 'foo'},
        {'id': 3, 'doc_type': 'bar'},
    ]

    def test__extract_set(self):
        """Test the _extract_set method."""
        obj = SearchQuery(hits=SearchQueryTests.hits)
        self.assertEqual(set(obj._extract_set('id')), set([1, 2, 3]))

    def test_doc_types(self):
        """Test the doc_types property."""
        obj = SearchQuery(hits=SearchQueryTests.hits)
        self.assertEqual(set(obj.doc_types), set(['foo', 'bar']))

    def test_object_ids(self):
        """Test the object_ids property."""
        obj = SearchQuery(hits=SearchQueryTests.hits)
        self.assertEqual(set(obj.object_ids), set([1, 2, 3]))

    def test_save(self):
        """Try saving unserializable JSON."""
        today = datetime.date.today()
        sq = SearchQuery(
            user=None,
            index='foo',
            query={'today': today},
            hits={'hits': decimal.Decimal('1.0')},
            total_hits=100,
            reference='bar',
            executed_at=tz_now(),
            duration=0
        )
        sq.save()
        sq.refresh_from_db()
        # invalid JSON values will have been converted
        self.assertEqual(sq.query['today'], today.isoformat())
        self.assertEqual(sq.hits['hits'], '1.0')

    def test_paging(self):
        """Test the paging properties."""
        sq = SearchQuery()
        self.assertEqual(sq.page_slice, None)

        # no hits, so should all be 0
        sq.query = {'from': 0, 'size': 25}
        self.assertEqual(sq.page_slice, (0, 25))
        self.assertEqual(sq.page_from, 0)
        self.assertEqual(sq.page_to, 0)
        self.assertEqual(sq.page_size, 0)

        # three hits
        sq.hits = [1, 2, 3]  # random list of size = 3
        sq.query = {'from': 0, 'size': 25}
        self.assertEqual(sq.page_from, 1)
        self.assertEqual(sq.page_to, 3)
        self.assertEqual(sq.page_size, 3)

    def test_scores(self):
        """Test the max/min properties."""
        sq = SearchQuery()
        self.assertEqual(sq.max_score, 0)
        self.assertEqual(sq.min_score, 0)

        sq.hits = [{'score': 1}, {'score': 2}]
        self.assertEqual(sq.max_score, 2)
        self.assertEqual(sq.min_score, 1)

    @mock.patch('elasticsearch_django.models.tz_now')
    @mock.patch.object(Search, 'execute')
    @mock.patch.object(Model, 'save')
    def test_execute(self, mock_save, mock_execute, mock_now):
        """Test the execute class method."""
        search = Search()
        sq = SearchQuery.execute(search)
        self.assertEqual(sq.user, None)
        self.assertEqual(sq.index, '_all')
        self.assertEqual(sq.query, search.to_dict())
        self.assertEqual(sq.hits, [])
        self.assertEqual(sq.total_hits, mock_execute.return_value.hits.total)
        self.assertEqual(sq.reference, '')
        self.assertTrue(sq.duration > 0)
        self.assertEqual(sq.executed_at, mock_now.return_value)
        mock_save.assert_called_once_with()

        # try without saving
        mock_save.reset_mock()
        sq = SearchQuery.execute(search, save=False)
        mock_save.assert_not_called()
