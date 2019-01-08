import datetime
import decimal
from unittest import mock

from django.db.models import Model
from django.test import TestCase
from django.utils.timezone import now as tz_now
from elasticsearch_dsl.search import Search

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

        # invalid action 'bar'
        self.assertRaises(ValueError, obj.as_search_action,  index="foo", action='bar')

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
        mock_qs.return_value.filter.assert_called_once_with(pk=1)
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
        self.maxDiff = None
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

        # test with a null score - new in v5
        sq = SearchQuery(hits=[{'id': 1, 'score': None}, {'id': 2, 'score': 2}])
        qs = TestModel.objects.from_search_query(sq)
        self.assertEqual(
            str(qs.query),
            'SELECT "elasticsearch_django_testmodel"."id", '
            '(SELECT CASE elasticsearch_django_testmodel."id" WHEN 1 THEN 0 WHEN 2 THEN 2 ELSE 0 END) '  # noqa
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
        self.assertEqual(sq.search_terms, '')
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
        self.assertEqual(sq.search_terms, '')
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
