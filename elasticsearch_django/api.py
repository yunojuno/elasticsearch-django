from __future__ import annotations

import datetime
from typing import Any, TypeAlias, cast

from django.conf import settings
from elastic_transport import ObjectApiResponse
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


class BaseOperation:
    """Base class used to execute and log search queries."""

    query_type: Any = ""

    def __init__(
        self,
        index: str | list[str],
        query: dict,
        response: ObjectApiResponse,
        duration: float = 0.0,
        executed_at: datetime.datetime | None = None,
    ) -> None:
        self.index = index
        self.query = query
        self.response = response
        self.duration = duration
        self.executed_at = executed_at

    @property
    def hits(self) -> list[SearchHitMetaType]:
        return []

    @property
    def aggregations(self) -> dict:
        return {}

    @property
    def max_score(self) -> float:
        return 0.0

    @property
    def total_hits(self) -> int:
        return 0

    @property
    def total_hits_relation(self) -> str:
        return ""

    @classmethod
    def do_execute(
        cls,
        *,
        index: str | list[str],
        query: dict,
        client: Elasticsearch = DEFAULT_CLIENT,
        **kwargs: Any,
    ) -> ObjectApiResponse:
        raise NotImplementedError

    @classmethod
    def execute(
        cls,
        *,
        index: str | list[str],
        query: dict,
        client: Elasticsearch = DEFAULT_CLIENT,
        **kwargs: Any,
    ) -> BaseOperation:
        with stopwatch() as timer:
            response = cls.do_execute(index=index, query=query, client=client, **kwargs)
        return cls(
            index=index,
            query=query,
            response=response,
            duration=timer.elapsed,
            executed_at=timer.started_at,
        )

    def save(
        self,
        user: settings.AUTH_USER_MODEL | None = None,
        search_terms: str = "",
        reference: str = "",
    ) -> SearchQuery:
        return SearchQuery.objects.create(
            user=user,
            search_terms=search_terms,
            reference=reference,
            index=self.index,
            query=self.query,
            query_type=self.query_type,
            hits=self.hits,
            aggregations=self.aggregations,
            total_hits=self.total_hits,
            total_hits_relation=self.total_hits_relation,
            executed_at=self.executed_at,
            duration=self.duration,
        )


class Search(BaseOperation):
    """
    Parse search response to make it easier to work with.

        >>> api.Search.execute(index=index, query=query).save()

    """

    query_type = SearchQuery.QueryType.SEARCH

    def __init__(
        self,
        index: str | list[str],
        query: dict,
        response: ObjectApiResponse,
        duration: float = 0.0,
        executed_at: datetime.datetime | None = None,
    ) -> None:
        super().__init__(index, query, response, duration, executed_at)
        self._hits = response.get("hits", {})
        self._total = self._hits.get("total", {})

    @property
    def hits(self) -> list[SearchHitMetaType]:
        return [
            {
                "index": h["_index"],
                "id": h["_id"],
                "score": h["_score"],
            }
            for h in self._hits.get("hits", {})
        ]

    @property
    def aggregations(self) -> dict:
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
    def do_execute(
        cls,
        *,
        index: str | list[str],
        query: dict,
        client: Elasticsearch = DEFAULT_CLIENT,
        **kwargs: Any,
    ) -> ObjectApiResponse:
        kwargs.setdefault("from_", DEFAULT_FROM)
        kwargs.setdefault("size", DEFAULT_PAGE_SIZE)
        return client.search(index=index, query=query, **kwargs)


class Count(BaseOperation):
    """
    Parse count response to make it easier to work with.

        >>> api.Count.execute(index=index, query=query).save()

    """

    query_type = SearchQuery.QueryType.COUNT

    @property
    def total_hits(self) -> int:
        return self.response.get("count", 0)

    @property
    def total_hits_relation(self) -> str:
        return str(SearchQuery.TotalHitsRelation.ACCURATE)

    @classmethod
    def do_execute(
        cls,
        *,
        index: str | list[str],
        query: dict,
        client: Elasticsearch = DEFAULT_CLIENT,
        **kwargs: Any,
    ) -> ObjectApiResponse:
        return client.count(index=index, query=query, **kwargs)
