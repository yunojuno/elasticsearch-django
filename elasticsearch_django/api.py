from __future__ import annotations

import time
from typing import TypeAlias

from django.utils.timezone import now as tz_now
from elasticsearch import Elasticsearch

from .context_manager import stopwatch
from .models import SearchQuery
from .settings import get_client, get_setting

DEFAULT_CLIENT = get_client()
DEFAULT_SEARCH_QUERY = {"match_all": {}}
DEFAULT_FROM = 0
DEFAULT_PAGE_SIZE = get_setting("page_size")


# Strongly-type the meta object we return from search
SearchHitMetaType: TypeAlias = dict[str, str | float]


class Search:
    """
    Parse search response to make it easier to work with.

    This class provides a classmethod to execute a search and parse the
    results:

        >>> search = Search.execute(index="blogs", query={"match_all": {}})
        >>> print(search.total_hits)
        10

    """

    def __init__(self, response: dict) -> None:
        self.raw = response
        self._hits = response.get("hits", {})
        self._total = self._hits.get("total", {})
        self.duration = None
        self.executed_at = None

    def _extract_hit(self, hit: dict) -> dict:
        return {
            "index": hit["_index"],
            "id": hit["_id"],
            "score": hit["_score"],
        }

    @property
    def hits(self) -> list[SearchHitMetaType]:
        """Return list of id, index, score dict for each hit returned."""
        return [self._extract_hit(h) for h in self._hits.get("hits", {})]

    @property
    def aggregations(self) -> dict:
        """Return raw aggregations from the response."""
        return self.raw.get("aggregations", {})

    @property
    def max_score(self) -> float:
        return self._hits.get("max_score", 0.0)

    @property
    def total_hits(self) -> int:
        return self._total.get("value", 0)

    @property
    def total_hits_relation(self) -> str:
        return self._total.get("relation", "")

    @classmethod
    def execute(
        cls,
        *,
        index: str | list[str],
        query: dict,
        client: Elasticsearch = DEFAULT_CLIENT,
        **search_kwargs,
    ) -> Search:
        start = time.time()
        with stopwatch() as timer:
            response = client.search(index=index, query=query, **search_kwargs)
        search = Search(
            index=index,
            query=query,
            response=response,
            duration=timer.elapsed,
            executed_at=timer.started_at,
        )
        return search

    def log(self, user, search_terms, reference) -> SearchQuery:
        return SearchQuery(
            user=user,
            search_terms=search_terms,
            index=self.inde,
            query=query,
            query_type=SearchQuery.QueryType.SEARCH,
            hits=self.hits,
            aggregations=self.aggregations,
            total_hits=self.total_hits,
            total_hits_relation=self.total_hits_relation,
            reference=reference or "",
            executed_at=self.executed_at,
            duration=self.duration,
        )


# search = Search.execute()
# search.log(user=me, reference="foo")
