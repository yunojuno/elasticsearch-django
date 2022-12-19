from __future__ import annotations

import datetime
from typing import TypeAlias, cast

from django.conf import settings
from elasticsearch import Elasticsearch

from .context_manager import stopwatch
from .models import SearchQuery
from .settings import get_client, get_setting

DEFAULT_CLIENT: Elasticsearch = get_client()
DEFAULT_SEARCH_QUERY: dict = {"match_all": {}}
DEFAULT_FROM: int = 0
DEFAULT_PAGE_SIZE = cast(int, get_setting("page_size"))


# Strongly-type the meta object we return from search
SearchHitMetaType: TypeAlias = dict[str, str | float]


class Search:
    """
    Parse search response to make it easier to work with.

    This class provides a classmethod to execute a search and parse the
    results.

    """

    def __init__(
        self,
        index: str | list[str],
        query: dict,
        response: dict,
        duration: float = 0.0,
        executed_at: datetime.datetime | None = None,
    ) -> None:
        self.index = index
        self.query = query
        self.response = response
        self._hits = response.get("hits", {})
        self._total = self._hits.get("total", {})
        self.duration = duration
        self.executed_at = executed_at

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
        return self.response.get("aggregations", {})

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
    ) -> Search:
        with stopwatch() as timer:
            response = client.search(index=index, **query)
        search = Search(
            index=index,
            query=query,
            response=response,
            duration=timer.elapsed,
            executed_at=timer.started_at,
        )
        return search

    def log(
        self,
        user: settings.AUTH_USER_MODEL,
        search_terms: str = "",
        reference: str = "",
    ) -> SearchQuery:
        return SearchQuery.objects.create(
            user=user,
            search_terms=search_terms,
            index=self.index,
            query=self.query,
            query_type=SearchQuery.QueryType.SEARCH,
            hits=self.hits,
            aggregations=self.aggregations,
            total_hits=self.total_hits,
            total_hits_relation=self.total_hits_relation,
            reference=reference or "",
            executed_at=self.executed_at,
            duration=self.duration,
        )
