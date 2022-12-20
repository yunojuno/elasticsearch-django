from unittest import mock

import pytest
from elasticsearch import Elasticsearch

from elasticsearch_django.api import Count, Search
from elasticsearch_django.models import SearchQuery


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
        mock_count.return_value = {
            "count": 562,
            "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
        }
        count = Count.execute(index="index", query={"match_all": {}})
        assert mock_count.call_count == 1
        mock_count.assert_called_with(index="index", query={"match_all": {}})
        assert count.total_hits == 562
        assert count.hits == []
        assert count.aggregations == {}

    @mock.patch.object(Elasticsearch, "count")
    def test_execute_count(self, mock_count):
        mock_count.return_value = {
            "count": 562,
            "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
        }
        sq = Count.execute(index="index", query={"match_all": {}}).save(
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
        assert sq.hits == []
        assert sq.total_hits == 562
        assert sq.total_hits_relation == SearchQuery.TotalHitsRelation.ACCURATE
        assert sq.query_type == SearchQuery.QueryType.COUNT
        assert sq.aggregations == {}
        assert sq.duration > 0

    @mock.patch.object(Elasticsearch, "search")
    def test_execute_search__no_save(self, mock_search: mock.MagicMock):
        mock_search.return_value = {
            "hits": {
                "total": {"value": 168, "relation": "gte"},
                "max_score": 1.1,
                "hits": self.raw_hits,
            },
            "aggregations": self.aggregations,
        }
        search = Search.execute(index="index", query={"match_all": {}})
        assert mock_search.call_count == 1
        mock_search.assert_called_with(
            index="index", query={"match_all": {}}, from_=0, size=25
        )
        assert search.total_hits == 168
        assert search.max_score == 1.1
        assert search.hits[0] == {"index": "foo", "id": "1", "score": 1.1}

    @mock.patch.object(Elasticsearch, "search")
    def test_execute_search(self, mock_search):
        # lots of mocking to get around lack of ES server during tests

        mock_search.return_value = {
            "hits": {
                "total": {"value": 168, "relation": "gte"},
                "max_score": 1.1,
                "hits": self.raw_hits,
            },
            "aggregations": self.aggregations,
        }
        sq = Search.execute(index="index", query={"match_all": {}}).save(
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
        assert sq.hits == self.clean_hits
        assert sq.total_hits == 168
        assert sq.total_hits_relation == SearchQuery.TotalHitsRelation.ESTIMATE
        assert sq.query_type == SearchQuery.QueryType.SEARCH
        assert sq.aggregations == self.aggregations
        assert sq.duration > 0
