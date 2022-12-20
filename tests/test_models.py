import datetime
import decimal
from unittest import mock
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.utils.timezone import now as tz_now
from elastic_transport import ObjectApiResponse
from elasticsearch import Elasticsearch

# from elasticsearch_django.api import Count, Search
from elasticsearch_django.models import (
    UPDATE_STRATEGY_FULL,
    UPDATE_STRATEGY_PARTIAL,
    SearchDocumentManagerMixin,
    SearchDocumentMixin,
    SearchQuery,
)

from .models import (
    ExampleModel,
    ExampleModelManager,
    ExampleModelWithCustomPrimaryKey,
    ModelA,
    ModelB,
)


class SearchDocumentMixinTests:
    """Tests for the SearchDocumentMixin."""

    @pytest.fixture
    def test_obj(self) -> ExampleModel:
        return ExampleModel(pk=1, simple_field_1=99, simple_field_2="foo")

    @mock.patch("elasticsearch_django.models.get_model_indexes")
    def test_search_indexes(self, mock_indexes, test_obj: ExampleModel):
        """Test the search_indexes function."""
        mock_indexes.return_value = "foo"
        assert test_obj.search_indexes == "foo", test_obj.search_indexes
        mock_indexes.assert_called_once_with(ExampleModel)

    def test_as_search_document(self):
        """Test the as_search_document method."""
        obj = SearchDocumentMixin()
        with pytest.raises(NotImplementedError):
            obj.as_search_document(index="_all")

    @mock.patch("elasticsearch_django.models.get_model_index_properties")
    def test_clean_update_fields(self, mock_properties, test_obj: ExampleModel):
        """Test that only fields in the mapping file are cleaned."""
        mock_properties.return_value = ["simple_field_1", "complex_field"]
        assert test_obj.clean_update_fields(
            index="", update_fields=["simple_field_1", "simple_field_2"]
        ) == ["simple_field_1"]

    @mock.patch("elasticsearch_django.models.get_model_index_properties")
    def test_clean_update_fields_related_field(
        self, mock_properties, test_obj: ExampleModel
    ):
        """Test that relation fields raise a ValueError."""
        test_obj = ExampleModel()
        mock_properties.return_value = ["simple_field_1", "user"]
        with pytest.raises(ValueError):
            test_obj.clean_update_fields(
                index="",
                update_fields=["simple_field_1", "complex_field", "user"],
            )

    @mock.patch("elasticsearch_django.models.get_model_index_properties")
    def test_as_search_document_update_full(
        self, mock_properties, test_obj: ExampleModel
    ):
        """Test the as_search_document_update method."""
        test_obj = ExampleModel(simple_field_1=1, simple_field_2="foo")
        mock_properties.return_value = ["simple_field_1"]
        with mock.patch(
            "elasticsearch_django.models.UPDATE_STRATEGY", UPDATE_STRATEGY_FULL
        ):
            assert test_obj.as_search_document_update(
                index="_all", update_fields=["simple_field_1"]
            ) == test_obj.as_search_document(index="_all")

    @mock.patch("elasticsearch_django.models.UPDATE_STRATEGY", UPDATE_STRATEGY_PARTIAL)
    @mock.patch("elasticsearch_django.models.get_model_index_properties")
    def test_as_search_document_update_partial(
        self, mock_properties, test_obj: ExampleModel
    ):
        """Test the as_search_document_update method."""
        mock_properties.return_value = ["simple_field_1", "simple_field_2"]
        assert test_obj.as_search_document_update(
            index="_all", update_fields=["simple_field_1", "simple_field_2"]
        ) == {
            "simple_field_1": test_obj.simple_field_1,
            "simple_field_2": test_obj.simple_field_2,
        }

        # remove simple_field_2 from the mapping - should no longer be included
        mock_properties.return_value = ["simple_field_1"]
        assert test_obj.as_search_document_update(
            index="_all", update_fields=["simple_field_1", "simple_field_2"]
        ) == {"simple_field_1": test_obj.simple_field_1}

    @mock.patch(
        "elasticsearch_django.settings.get_connection_string",
        lambda: "http://testserver",
    )
    @mock.patch("elasticsearch_django.models.get_client")
    def test_index_search_document(self, mock_client, test_obj: ExampleModel):
        """Test the index_search_document sets the cache."""
        # obj = ExampleModel(pk=1, simple_field_1=1, simple_field_2="foo")
        doc = test_obj.as_search_document(index="_all")
        key = test_obj.search_document_cache_key
        assert cache.get(key) is None
        test_obj.index_search_document(index="_all")
        assert cache.get(key) == doc
        mock_client.return_value.index.assert_called_once_with(
            index="_all",
            document=doc,
            id=test_obj.get_search_document_id(),
        )

    @mock.patch(
        "elasticsearch_django.settings.get_connection_string",
        lambda: "http://testserver",
    )
    @mock.patch("elasticsearch_django.models.get_client")
    def test_index_search_document_cached(self, mock_client, test_obj: ExampleModel):
        """Test the index_search_document does not update if doc is a duplicate."""
        doc = test_obj.as_search_document(index="_all")
        key = test_obj.search_document_cache_key
        cache.set(key, doc, timeout=1)
        assert cache.get(key) == doc
        test_obj.index_search_document(index="_all")
        assert mock_client.call_count == 0

    @mock.patch(
        "elasticsearch_django.settings.get_connection_string",
        lambda: "http://testserver",
    )
    @mock.patch("elasticsearch_django.models.get_setting")
    @mock.patch("elasticsearch_django.models.get_client")
    def test_update_search_document(
        self, mock_client, mock_setting, test_obj: ExampleModel
    ):
        """Test the update_search_document wraps up doc correctly."""
        doc = test_obj.as_search_document_update(
            index="_all", update_fields=["simple_field_1"]
        )
        test_obj.update_search_document(index="_all", update_fields=["simple_field_1"])
        mock_client.return_value.update.assert_called_once_with(
            index="_all",
            id=test_obj.get_search_document_id(),
            doc=doc,
            retry_on_conflict=mock_setting.return_value,
        )
        mock_setting.assert_called_once_with("retry_on_conflict", 0)

    @mock.patch(
        "elasticsearch_django.settings.get_connection_string",
        lambda: "http://testserver",
    )
    @mock.patch("elasticsearch_django.models.get_client")
    def test_update_search_document_empty(self, mock_client, test_obj: ExampleModel):
        """Test the update_search_document ignores empty updates."""
        with mock.patch.object(
            ExampleModel, "as_search_document_update"
        ) as mock_update:
            mock_update.return_value = {}
            # this will return an empty dictionary as the partial update doc
            test_obj.update_search_document(index="_all", update_fields=[])
            mock_client.return_value.update.assert_not_called()

    @mock.patch(
        "elasticsearch_django.settings.get_connection_string",
        lambda: "http://testserver",
    )
    @mock.patch("elasticsearch_django.models.get_client")
    def test_delete_search_document(self, mock_client, test_obj: ExampleModel):
        """Test the delete_search_document clears the cache."""
        doc = test_obj.as_search_document(index="_all")
        key = test_obj.search_document_cache_key
        cache.set(key, doc)
        assert cache.get(key) is not None
        test_obj.delete_search_document(index="_all")
        assert cache.get(key) is None
        mock_client.return_value.delete.assert_called_once_with(
            index="_all", id=test_obj.get_search_document_id()
        )

    def test_as_search_action(self, test_obj: ExampleModel):
        """Test the as_search_action method."""
        # invalid action 'bar'
        with pytest.raises(ValueError):
            test_obj.as_search_action(index="foo", action="bar")

        assert test_obj.as_search_action(index="foo", action="index") == {
            "_index": "foo",
            "_op_type": "index",
            "_id": test_obj.get_search_document_id(),
            "_source": test_obj.as_search_document(),
        }

        assert test_obj.as_search_action(index="foo", action="update") == {
            "_index": "foo",
            "_op_type": "update",
            "_id": test_obj.get_search_document_id(),
            "doc": test_obj.as_search_document(),
        }

        assert test_obj.as_search_action(index="foo", action="delete") == {
            "_index": "foo",
            "_op_type": "delete",
            "_id": test_obj.get_search_document_id(),
        }

    @mock.patch("elasticsearch_django.models.get_client")
    def test_fetch_search_document(self, mock_client):
        """Test the fetch_search_document method."""
        obj = ExampleModel()
        # obj has no id
        with pytest.raises(ValueError):
            obj.fetch_search_document(index="foo")

        # should now call the ES get method
        obj.id = 1
        response = obj.fetch_search_document(index="foo")
        mock_get = mock_client.return_value.get
        mock_get.assert_called_once_with(index="foo", id=obj.get_search_document_id())
        assert response == mock_get.return_value


class SearchDocumentManagerMixinTests:
    """Tests for the SearchDocumentManagerMixin."""

    def test_get_search_queryset(self):
        """Test the get_search_queryset method."""
        obj = SearchDocumentManagerMixin()
        with pytest.raises(NotImplementedError):
            obj.get_search_queryset()

    @mock.patch.object(ExampleModelManager, "get_search_queryset")
    def test_in_search_queryset(self, mock_qs):
        """Test the in_search_queryset method."""
        obj = ExampleModel(id=1, simple_field_1=1, simple_field_2="foo")
        ExampleModel.objects.in_search_queryset(obj.get_search_document_id())
        mock_qs.assert_called_once_with(index="_all")
        mock_qs.return_value.filter.assert_called_once_with(
            pk=obj.get_search_document_id()
        )
        mock_qs.return_value.filter.return_value.exists.assert_called_once_with()

    @mock.patch.object(ExampleModelManager, "get_search_queryset")
    def test_in_search_queryset_with_a_model_using_custom_primary_key(self, mock_qs):
        """Test the in_search_queryset method."""
        obj = ExampleModelWithCustomPrimaryKey(simple_field_1=1)
        ExampleModelWithCustomPrimaryKey.objects.in_search_queryset(
            obj.get_search_document_id()
        )
        mock_qs.assert_called_once_with(index="_all")
        mock_qs.return_value.filter.assert_called_once_with(pk="1")
        mock_qs.return_value.filter.return_value.exists.assert_called_once_with()

    @mock.patch("django.db.models.query.QuerySet")
    def test_from_search_query(self, mock_qs):
        """Test the from_search_query method."""
        self.maxDiff = None
        sq = SearchQuery(
            query={"query": {"match_all": {}}},
            hits=[{"id": "1", "score": 1.0}, {"id": "2", "score": 2.0}],
        )
        qs = ExampleModel.objects.all().from_search_results(sq)
        assert str(qs.query) == (
            'SELECT "tests_examplemodel"."id", "tests_examplemodel"."user_id", "tests_examplemodel"."simple_field_1", '
            '"tests_examplemodel"."simple_field_2", "tests_examplemodel"."complex_field", '
            'CASE WHEN "tests_examplemodel"."id" = 1 THEN 1 WHEN "tests_examplemodel"."id" = 2 '
            'THEN 2 ELSE NULL END AS "search_rank", CASE WHEN "tests_examplemodel"."id" = 1 '
            'THEN 1.0 WHEN "tests_examplemodel"."id" = 2 THEN 2.0 ELSE NULL END AS "search_score" '
            'FROM "tests_examplemodel" WHERE "tests_examplemodel"."id" IN (1, 2) '
            'ORDER BY "search_rank" ASC'
        )

        # test with a null score - new in v5
        sq = SearchQuery(
            query={"query": {"match_all": {}}},
            hits=[{"id": 1, "score": None}, {"id": 2, "score": 2}],
        )
        qs = ExampleModel.objects.all().from_search_results(sq)
        assert str(qs.query) == (
            'SELECT "tests_examplemodel"."id", "tests_examplemodel"."user_id", '
            '"tests_examplemodel"."simple_field_1", "tests_examplemodel"."simple_field_2", '
            '"tests_examplemodel"."complex_field", CASE WHEN "tests_examplemodel"."id" = 1 '
            'THEN 1 WHEN "tests_examplemodel"."id" = 2 '
            'THEN 2 ELSE NULL END AS "search_rank", CASE WHEN "tests_examplemodel"."id" = 1 '
            'THEN NULL WHEN "tests_examplemodel"."id" = 2 THEN 2.0 ELSE NULL END AS "search_score" '
            'FROM "tests_examplemodel" WHERE "tests_examplemodel"."id" IN (1, 2) '
            'ORDER BY "search_rank" ASC'
        )


@pytest.mark.django_db
class SearchQueryTests:
    """Tests for the SearchQuery model."""

    hits = [
        {"id": "1", "doc_type": "foo"},
        {"id": "2", "doc_type": "foo"},
        {"id": "3", "doc_type": "bar"},
    ]

    hits_with_highlights = [
        {"id": "1", "doc_type": "foo", "highlight": {"field1": ["bar"]}},
        {"id": "2", "doc_type": "foo"},
        {"id": "3", "doc_type": "bar"},
    ]

    def test__hit_values(self):
        """Test the _hit_values method."""
        obj = SearchQuery(hits=self.hits)
        assert set(obj._hit_values("id")) == {"1", "2", "3"}

    def test_object_ids(self):
        """Test the object_ids property."""
        obj = SearchQuery(hits=self.hits)
        assert set(obj.object_ids) == {"1", "2", "3"}

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
        assert sq.search_terms == ""
        assert sq.query["today"] == today.isoformat()
        assert sq.hits["hits"] == "1.0"
        assert sq.query_type == SearchQuery.QueryType.SEARCH
        assert sq.aggregations is None

    def test_paging(self):
        """Test the paging properties."""
        sq = SearchQuery()
        assert sq.page_slice is None

        # no hits, so should all be 0
        sq.query = {"from": 0, "size": 25}
        assert sq.page_slice == (0, 25)
        assert sq.page_from == 0
        assert sq.page_to == 0
        assert sq.page_size == 0

        # three hits
        sq.hits = [1, 2, 3]  # random list of size = 3
        sq.query = {"from": 0, "size": 25}
        assert sq.page_from == 1
        assert sq.page_to == 3
        assert sq.page_size == 3

    def test_scores(self):
        """Test the max/min properties."""
        sq = SearchQuery()
        assert sq.max_score == 0
        assert sq.min_score == 0

        sq.hits = [{"score": 1}, {"score": 2}]
        assert sq.max_score == 2
        assert sq.min_score == 1

    def test_has_highlights(self):
        sq = SearchQuery(query={"highlight": {}})
        assert sq.has_highlights
        sq = SearchQuery(query={"query": {"match_all": {}}})
        assert not sq.has_highlights

    def test_get_doc_highlights(self):
        sq = SearchQuery(query={"highlight": {}}, hits=self.hits_with_highlights)
        assert sq.get_doc_highlights(1) == {"field1": ["bar"]}


@pytest.mark.django_db
class SearchResultsQuerySetTests:
    def hits(self):
        return [
            {"id": str(uuid4()), "score": 3.0},
            {"id": str(uuid4()), "score": 2.0},
            {"id": str(uuid4()), "score": 1.0},
        ]

    def test_from_search_results(self) -> None:
        hits = self.hits()
        model_a1 = ModelA.objects.create(field_1=hits[0]["id"], field_2="foo")
        model_b = ModelB.objects.create(source=model_a1)
        assert model_b.as_search_document(index="") == {
            "field_2": "foo",
            "extra_info": "some other data",
        }
        sq = SearchQuery(hits=hits)
        qs = ModelA.objects.from_search_results(sq)
        obj = qs.get()
        assert obj == model_a1
        assert obj.search_rank == 1
        assert obj.search_score == 3.0


@pytest.mark.django_db
class ExecuteFunctionTests:

    raw_hits = [
        {"_id": "1", "_index": "foo", "_score": 1.1},
        {"_id": "2", "_index": "foo", "_score": 1.2},
        {"_id": "3", "_index": "bar", "_score": 1.3},
    ]
    clean_hits = [
        {"id": "1", "index": "foo", "score": 1.1},
        {"id": "2", "index": "foo", "score": 1.2},
        {"id": "3", "index": "bar", "score": 1.3},
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

    @mock.patch.object(Elasticsearch, "count")
    def test_execute_count__no_save(self, mock_count: mock.MagicMock) -> None:
        mock_count.return_value = mock.Mock(
            spec=ObjectApiResponse,
            body={
                "count": 562,
                "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            },
        )
        count = SearchQuery.do_count(index="index", query={"match_all": {}})
        assert mock_count.call_count == 1
        mock_count.assert_called_with(index="index", query={"match_all": {}})
        assert count.total_hits == 562
        assert count.hits is None
        assert count.aggregations is None

    @mock.patch.object(Elasticsearch, "count")
    def test_execute_count(self, mock_count):
        mock_count.return_value = mock.Mock(
            spec=ObjectApiResponse,
            body={
                "count": 562,
                "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            },
        )
        sq = SearchQuery.do_count(index="index", query={"match_all": {}}).save(
            search_terms="foo",
            user=None,
            reference="bar",
        )
        sq.refresh_from_db()  # just to confirm it saves in / out
        assert sq.id is not None
        assert sq.search_terms == "foo"
        assert sq.reference == "bar"
        assert sq.query == {"match_all": {}}
        assert sq.index == "index"
        assert sq.hits is None
        assert sq.total_hits == 562
        assert sq.total_hits_relation == SearchQuery.TotalHitsRelation.ACCURATE
        assert sq.query_type == SearchQuery.QueryType.COUNT
        assert sq.aggregations is None
        assert sq.duration > 0

    @mock.patch.object(Elasticsearch, "search")
    def test_execute_search__no_save(self, mock_search: mock.MagicMock):
        mock_search.return_value = mock.Mock(
            spec=ObjectApiResponse,
            body={
                "hits": {
                    "total": {"value": 168, "relation": "gte"},
                    "max_score": 1.3,
                    "hits": self.raw_hits,
                },
                "aggregations": self.aggregations,
            },
        )
        search = SearchQuery.do_search(index="index", query={"match_all": {}})
        assert mock_search.call_count == 1
        mock_search.assert_called_with(
            index="index", query={"match_all": {}}, from_=0, size=25
        )
        assert search.total_hits == 168
        assert search.max_score == 1.3
        assert search.hits[0] == {"index": "foo", "id": "1", "score": 1.1}

    @mock.patch.object(Elasticsearch, "search")
    def test_execute_search(self, mock_search):
        # lots of mocking to get around lack of ES server during tests

        mock_search.return_value = mock.Mock(
            spec=ObjectApiResponse,
            body={
                "hits": {
                    "total": {"value": 168, "relation": "gte"},
                    "max_score": 1.1,
                    "hits": self.raw_hits,
                },
                "aggregations": self.aggregations,
            },
        )
        sq = SearchQuery.do_search(index="index", query={"match_all": {}}).save(
            search_terms="foo",
            user=None,
            reference="bar",
        )
        sq.refresh_from_db()  # just to confirm it saves in / out
        assert sq.id is not None
        assert sq.search_terms == "foo"
        assert sq.reference == "bar"
        assert sq.query == {"query": {"match_all": {}}, "from_": 0, "size": 25}
        assert sq.index == "index"
        assert sq.hits == self.clean_hits
        assert sq.total_hits == 168
        assert sq.total_hits_relation == SearchQuery.TotalHitsRelation.ESTIMATE
        assert sq.query_type == SearchQuery.QueryType.SEARCH
        assert sq.aggregations == self.aggregations
        assert sq.duration > 0
