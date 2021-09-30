import datetime
import decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils.timezone import now as tz_now
from elasticsearch_dsl.response import AggResponse, Hit, HitMeta, Response
from elasticsearch_dsl.search import Search

from elasticsearch_django.models import (
    UPDATE_STRATEGY_FULL,
    UPDATE_STRATEGY_PARTIAL,
    SearchDocumentManagerMixin,
    SearchDocumentMixin,
    SearchQuery,
    execute_count,
    execute_search,
)

from .models import ExampleModel, ExampleModelManager


class SearchDocumentMixinTests(TestCase):
    """Tests for the SearchDocumentMixin."""

    @mock.patch("elasticsearch_django.models.get_model_indexes")
    def test_search_indexes(self, mock_indexes):
        """Test the search_indexes function."""
        mock_indexes.return_value = "foo"
        obj = ExampleModel()
        self.assertEqual(obj.search_indexes, "foo")
        mock_indexes.assert_called_once_with(ExampleModel)

    def test_as_search_document(self):
        """Test the as_search_document method."""
        obj = SearchDocumentMixin()
        self.assertRaises(NotImplementedError, obj.as_search_document, index="_all")

    def test__is_field_serializable(self):
        obj = ExampleModel()
        self.assertTrue(obj._is_field_serializable("simple_field_1"))
        self.assertTrue(obj._is_field_serializable("simple_field_1"))
        self.assertFalse(obj._is_field_serializable("complex_field"))

    @mock.patch("elasticsearch_django.models.get_model_index_properties")
    def test_clean_update_fields(self, mock_properties):
        """Test that only fields in the mapping file are cleaned."""
        obj = ExampleModel()
        mock_properties.return_value = ["simple_field_1", "complex_field"]
        self.assertEqual(
            obj.clean_update_fields(
                index="", update_fields=["simple_field_1", "simple_field_2"]
            ),
            ["simple_field_1"],
        )

    @mock.patch("elasticsearch_django.models.get_model_index_properties")
    def test_clean_update_fields_complex_object(self, mock_properties):
        """Test that unserializable fields raise a ValueError."""
        obj = ExampleModel()
        mock_properties.return_value = ["simple_field_1", "complex_field"]
        self.assertRaises(
            ValueError,
            obj.clean_update_fields,
            index="",
            update_fields=["simple_field_1", "complex_field"],
        )

    @mock.patch("elasticsearch_django.models.get_model_index_properties")
    def test_as_search_document_update_full(self, mock_properties):
        """Test the as_search_document_update method."""
        obj = ExampleModel(simple_field_1=1, simple_field_2="foo")
        mock_properties.return_value = ["simple_field_1"]
        with mock.patch(
            "elasticsearch_django.models.UPDATE_STRATEGY", UPDATE_STRATEGY_FULL
        ):
            self.assertEqual(
                obj.as_search_document_update(
                    index="_all", update_fields=["simple_field_1"]
                ),
                obj.as_search_document(index="_all"),
            )

    @mock.patch("elasticsearch_django.models.UPDATE_STRATEGY", UPDATE_STRATEGY_PARTIAL)
    @mock.patch("elasticsearch_django.models.get_model_index_properties")
    def test_as_search_document_update_partial(self, mock_properties):
        """Test the as_search_document_update method."""
        obj = ExampleModel(simple_field_1=1, simple_field_2="foo")
        mock_properties.return_value = ["simple_field_1", "simple_field_2"]
        self.assertEqual(
            obj.as_search_document_update(
                index="_all", update_fields=["simple_field_1", "simple_field_2"]
            ),
            {
                "simple_field_1": obj.simple_field_1,
                "simple_field_2": obj.simple_field_2,
            },
        )
        # remove simple_field_2 from the mapping - should no longer be included
        mock_properties.return_value = ["simple_field_1"]
        self.assertEqual(
            obj.as_search_document_update(
                index="_all", update_fields=["simple_field_1", "simple_field_2"]
            ),
            {"simple_field_1": obj.simple_field_1},
        )

    @mock.patch(
        "elasticsearch_django.settings.get_connection_string",
        lambda: "http://testserver",
    )
    @mock.patch("elasticsearch_django.models.get_client")
    def test_index_search_document(self, mock_client):
        """Test the index_search_document sets the cache."""
        obj = ExampleModel(pk=1)
        doc = obj.as_search_document(index="_all")
        key = obj.search_document_cache_key
        self.assertIsNone(cache.get(key))
        obj.index_search_document(index="_all")
        self.assertEqual(cache.get(key), doc)
        mock_client.return_value.index.assert_called_once_with(
            body=doc, id=1, index="_all"
        )

    @mock.patch(
        "elasticsearch_django.settings.get_connection_string",
        lambda: "http://testserver",
    )
    @mock.patch("elasticsearch_django.models.get_client")
    def test_index_search_document_cached(self, mock_client):
        """Test the index_search_document does not update if doc is a duplicate."""
        obj = ExampleModel(pk=1)
        doc = obj.as_search_document(index="_all")
        key = obj.search_document_cache_key
        cache.set(key, doc, timeout=1)
        self.assertEqual(cache.get(key), doc)
        obj.index_search_document(index="_all")
        self.assertEqual(mock_client.call_count, 0)

    @mock.patch(
        "elasticsearch_django.settings.get_connection_string",
        lambda: "http://testserver",
    )
    @mock.patch("elasticsearch_django.models.get_setting")
    @mock.patch("elasticsearch_django.models.get_client")
    def test_update_search_document(self, mock_client, mock_setting):
        """Test the update_search_document wraps up doc correctly."""
        obj = ExampleModel(pk=1, simple_field_1=1)
        doc = obj.as_search_document_update(
            index="_all", update_fields=["simple_field_1"]
        )
        obj.update_search_document(index="_all", update_fields=["simple_field_1"])
        mock_client.return_value.update.assert_called_once_with(
            index="_all",
            id=1,
            body={"doc": doc},
            retry_on_conflict=mock_setting.return_value,
        )
        mock_setting.assert_called_once_with("retry_on_conflict", 0)

    @mock.patch(
        "elasticsearch_django.settings.get_connection_string",
        lambda: "http://testserver",
    )
    @mock.patch("elasticsearch_django.models.get_client")
    def test_update_search_document_empty(self, mock_client):
        """Test the update_search_document ignores empty updates."""
        obj = ExampleModel(pk=1, simple_field_1=1)
        with mock.patch.object(
            ExampleModel, "as_search_document_update"
        ) as mock_update:
            mock_update.return_value = {}
            # this will return an empty dictionary as the partial update doc
            obj.update_search_document(index="_all", update_fields=[])
            mock_client.return_value.update.assert_not_called()

    @mock.patch(
        "elasticsearch_django.settings.get_connection_string",
        lambda: "http://testserver",
    )
    @mock.patch("elasticsearch_django.models.get_client")
    def test_delete_search_document(self, mock_client):
        """Test the delete_search_document clears the cache."""
        obj = ExampleModel(pk=1)
        doc = obj.as_search_document(index="_all")
        key = obj.search_document_cache_key
        cache.set(key, doc)
        self.assertIsNotNone(cache.get(key))
        obj.delete_search_document(index="_all")
        self.assertIsNone(cache.get(key))
        mock_client.return_value.delete.assert_called_once_with(id=1, index="_all")

    def test_as_search_action(self):
        """Test the as_search_action method."""
        obj = ExampleModel()

        # invalid action 'bar'
        self.assertRaises(ValueError, obj.as_search_action, index="foo", action="bar")

        self.assertEqual(
            obj.as_search_action(index="foo", action="index"),
            {
                "_index": "foo",
                "_op_type": "index",
                "_id": None,
                "_source": obj.as_search_document(),
            },
        )

        self.assertEqual(
            obj.as_search_action(index="foo", action="update"),
            {
                "_index": "foo",
                "_op_type": "update",
                "_id": None,
                "doc": obj.as_search_document(),
            },
        )

        self.assertEqual(
            obj.as_search_action(index="foo", action="delete"),
            {"_index": "foo", "_op_type": "delete", "_id": None},
        )

    @mock.patch("elasticsearch_django.models.get_client")
    def test_fetch_search_document(self, mock_client):
        """Test the fetch_search_document method."""
        obj = ExampleModel()
        # obj has no id
        self.assertRaises(ValueError, obj.fetch_search_document, index="foo")

        # should now call the ES get method
        obj.id = 1
        response = obj.fetch_search_document(index="foo")
        mock_get = mock_client.return_value.get
        mock_get.assert_called_once_with(index="foo", id=obj.id)
        self.assertEqual(response, mock_get.return_value)


class SearchDocumentManagerMixinTests(TestCase):
    """Tests for the SearchDocumentManagerMixin."""

    def test_get_search_queryset(self):
        """Test the get_search_queryset method."""
        obj = SearchDocumentManagerMixin()
        self.assertRaises(NotImplementedError, obj.get_search_queryset)

    @mock.patch.object(ExampleModelManager, "get_search_queryset")
    def test_in_search_queryset(self, mock_qs):
        """Test the in_search_queryset method."""
        obj = ExampleModel(id=1)
        ExampleModel.objects.in_search_queryset(obj.id)
        mock_qs.assert_called_once_with(index="_all")
        mock_qs.return_value.filter.assert_called_once_with(pk=1)
        mock_qs.return_value.filter.return_value.exists.assert_called_once_with()

    def test__raw_sql(self):
        """Test the _raw_sql method."""
        self.assertEqual(
            ExampleModel.objects._raw_sql(((1, 2), (3, 4))),
            'SELECT CASE tests_examplemodel."id" '
            "WHEN 1 THEN 2 WHEN 3 THEN 4 ELSE 0 END",
        )

    @mock.patch("django.db.models.query.QuerySet")
    def test_from_search_query(self, mock_qs):
        """Test the from_search_query method."""
        self.maxDiff = None
        sq = SearchQuery(hits=[{"id": 1, "score": 1}, {"id": 2, "score": 2}])
        qs = ExampleModel.objects.from_search_query(sq)
        self.assertEqual(
            str(qs.query),
            'SELECT "tests_examplemodel"."id", "tests_examplemodel"."simple_field_1", '  # noqa
            '"tests_examplemodel"."simple_field_2", "tests_examplemodel"."complex_field", '  # noqa
            '(SELECT CASE tests_examplemodel."id" WHEN 1 THEN 1 WHEN 2 THEN 2 ELSE 0 END) AS "search_score", '  # noqa
            '(SELECT CASE tests_examplemodel."id" WHEN 1 THEN 0 WHEN 2 THEN 1 ELSE 0 END) AS "search_rank" '  # noqa
            'FROM "tests_examplemodel" WHERE "tests_examplemodel"."id" IN (1, 2) ORDER BY "search_rank" ASC',  # noqa
        )

        # test with a null score - new in v5
        sq = SearchQuery(hits=[{"id": 1, "score": None}, {"id": 2, "score": 2}])
        qs = ExampleModel.objects.from_search_query(sq)
        self.assertEqual(
            str(qs.query),
            'SELECT "tests_examplemodel"."id", "tests_examplemodel"."simple_field_1", '  # noqa
            '"tests_examplemodel"."simple_field_2", "tests_examplemodel"."complex_field", '  # noqa
            '(SELECT CASE tests_examplemodel."id" WHEN 1 THEN 0 WHEN 2 THEN 2 ELSE 0 END) AS "search_score", '  # noqa
            '(SELECT CASE tests_examplemodel."id" WHEN 1 THEN 0 WHEN 2 THEN 1 ELSE 0 END) AS "search_rank" '  # noqa
            'FROM "tests_examplemodel" WHERE "tests_examplemodel"."id" IN (1, 2) ORDER BY "search_rank" ASC',  # noqa
        )


class SearchQueryTests(TestCase):
    """Tests for the SearchQuery model."""

    hits = [
        {"id": 1, "doc_type": "foo"},
        {"id": 2, "doc_type": "foo"},
        {"id": 3, "doc_type": "bar"},
    ]

    def test__extract_set(self):
        """Test the _extract_set method."""
        obj = SearchQuery(hits=SearchQueryTests.hits)
        self.assertEqual(set(obj._extract_set("id")), {1, 2, 3})

    def test_object_ids(self):
        """Test the object_ids property."""
        obj = SearchQuery(hits=SearchQueryTests.hits)
        self.assertEqual(set(obj.object_ids), {1, 2, 3})

    def test_save(self):
        """Try saving unserializable JSON."""
        today = datetime.date.today()
        sq = SearchQuery(
            user=None,
            index="foo",
            query={"today": today},
            hits={"hits": decimal.Decimal("1.0")},
            total_hits=100,
            reference="bar",
            executed_at=tz_now(),
            duration=0,
        )
        sq.save()
        sq.refresh_from_db()
        # invalid JSON values will have been converted
        self.assertEqual(sq.search_terms, "")
        self.assertEqual(sq.query["today"], today.isoformat())
        self.assertEqual(sq.hits["hits"], "1.0")
        self.assertEqual(sq.query_type, SearchQuery.QueryType.SEARCH)
        self.assertEqual(sq.aggregations, {})

    def test_paging(self):
        """Test the paging properties."""
        sq = SearchQuery()
        self.assertEqual(sq.page_slice, None)

        # no hits, so should all be 0
        sq.query = {"from": 0, "size": 25}
        self.assertEqual(sq.page_slice, (0, 25))
        self.assertEqual(sq.page_from, 0)
        self.assertEqual(sq.page_to, 0)
        self.assertEqual(sq.page_size, 0)

        # three hits
        sq.hits = [1, 2, 3]  # random list of size = 3
        sq.query = {"from": 0, "size": 25}
        self.assertEqual(sq.page_from, 1)
        self.assertEqual(sq.page_to, 3)
        self.assertEqual(sq.page_size, 3)

    def test_scores(self):
        """Test the max/min properties."""
        sq = SearchQuery()
        self.assertEqual(sq.max_score, 0)
        self.assertEqual(sq.min_score, 0)

        sq.hits = [{"score": 1}, {"score": 2}]
        self.assertEqual(sq.max_score, 2)
        self.assertEqual(sq.min_score, 1)


class ExecuteFunctionTests(TestCase):

    hits = [
        {"id": 1, "doc_type": "foo"},
        {"id": 2, "doc_type": "foo"},
        {"id": 3, "doc_type": "bar"},
    ]

    aggregations = {
        "test_percentiles": {
            "values": {
                "1.0": 10.0,
                "5.0": 15.0,
                "25.0": 200.0,
                "50.0": 350.0,
                "75.0": 400.0,
                "95.0": 600.0,
                "99.0": 1500.0,
            }
        }
    }

    @mock.patch.object(Search, "count")
    def test_execute_count__no_save(self, mock_count):
        search = Search()
        sq = execute_count(search, save=False)
        self.assertIsNone(sq.id)

    @mock.patch.object(Search, "count")
    def test_execute_count(self, mock_count):
        mock_count.return_value = 100
        search = Search()
        sq = execute_count(search, search_terms="foo", user=None, reference="bar")
        sq.refresh_from_db()  # just to confirm it saves in / out
        self.assertIsNotNone(sq.id)
        self.assertEqual(sq.search_terms, "foo")
        self.assertEqual(sq.reference, "bar")
        self.assertEqual(sq.query, search.to_dict())
        self.assertEqual(sq.index, "_all")
        self.assertEqual(sq.hits, [])
        self.assertEqual(sq.total_hits, 100)
        self.assertEqual(sq.total_hits_relation, SearchQuery.TotalHitsRelation.ACCURATE)
        self.assertEqual(sq.query_type, SearchQuery.QueryType.COUNT)
        self.assertEqual(sq.aggregations, {})
        self.assertTrue(sq.duration > 0)

    @mock.patch.object(Search, "execute")
    def test_execute_search__no_save(self, mock_count):
        search = Search()
        sq = execute_search(search, save=False)
        self.assertIsNone(sq.id)

    @mock.patch.object(Search, "execute")
    def test_execute_search(self, mock_search):
        # lots of mocking to get around lack of ES server during tests

        def mock_hit(meta_dict):
            # Returns a mock that looks like a Hit
            hm = mock.Mock(spec=HitMeta)
            hm.to_dict.return_value = meta_dict
            return mock.Mock(spec=Hit, meta=hm)

        response = mock.MagicMock(spec=Response)
        response.hits.__iter__.return_value = iter(
            [mock_hit(h) for h in ExecuteFunctionTests.hits]
        )
        response.hits.total.value = 100
        response.hits.total.relation = "gte"
        response.aggregations = mock.Mock(spec=AggResponse)
        response.aggregations.to_dict.return_value = ExecuteFunctionTests.aggregations
        mock_search.return_value = response

        search = Search()
        sq = execute_search(search, search_terms="foo", user=None, reference="bar")
        sq.refresh_from_db()  # just to confirm it saves in / out
        self.assertIsNotNone(sq.id)
        self.assertEqual(sq.search_terms, "foo")
        self.assertEqual(sq.reference, "bar")
        self.assertEqual(sq.query, search.to_dict())
        self.assertEqual(sq.index, "_all")
        self.assertEqual(sq.hits, ExecuteFunctionTests.hits)
        self.assertEqual(sq.total_hits, 100)
        self.assertEqual(sq.total_hits_relation, SearchQuery.TotalHitsRelation.ESTIMATE)
        self.assertEqual(sq.query_type, SearchQuery.QueryType.SEARCH)
        self.assertEqual(sq.aggregations, ExecuteFunctionTests.aggregations)
        self.assertTrue(sq.duration > 0)
