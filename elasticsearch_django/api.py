from __future__ import annotations

import datetime
from typing import Any, TypeAlias, cast

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


class BaseOperation:
    """Base class used to execute and log search queries."""

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
        self.duration = duration
        self.executed_at = executed_at

    @property
    def hits(self) -> list[SearchHitMetaType]:
        raise NotImplementedError

    @property
    def aggregations(self) -> dict:
        raise NotImplementedError

    @property
    def max_score(self) -> float:
        raise NotImplementedError

    @property
    def total_hits(self) -> int:
        raise NotImplementedError

    @property
    def total_hits_relation(self) -> str:
        raise NotImplementedError

    @property
    def query_type(self) -> str:
        raise NotImplementedError

    @classmethod
    def do_execute(
        cls,
        *,
        index: str | list[str],
        query: dict,
        client: Elasticsearch = DEFAULT_CLIENT,
        **kwargs: Any,
    ) -> dict:
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

    def __init__(
        self,
        index: str | list[str],
        query: dict,
        response: dict,
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

    @property
    def query_type(self) -> str:
        return str(SearchQuery.QueryType.SEARCH)

    @classmethod
    def do_execute(
        cls,
        *,
        index: str | list[str],
        query: dict,
        client: Elasticsearch = DEFAULT_CLIENT,
        **kwargs: Any,
    ) -> dict:
        kwargs.setdefault("from_", DEFAULT_FROM)
        kwargs.setdefault("size", DEFAULT_PAGE_SIZE)
        return client.search(index=index, query=query, **kwargs)


class Count(BaseOperation):
    """
    Parse count response to make it easier to work with.

        >>> api.Count.execute(index=index, query=query).save()

    """

    @property
    def hits(self) -> list[SearchHitMetaType]:
        return []

    @property
    def aggregations(self) -> dict:
        return {}

    @property
    def total_hits(self) -> int:
        return self.response.get("count", 0)

    @property
    def total_hits_relation(self) -> str:
        return str(SearchQuery.TotalHitsRelation.ACCURATE)

    @property
    def query_type(self) -> str:
        return str(SearchQuery.QueryType.COUNT)

    @classmethod
    def do_execute(
        cls,
        *,
        index: str | list[str],
        query: dict,
        client: Elasticsearch = DEFAULT_CLIENT,
        **kwargs: Any,
    ) -> dict:
        return client.count(index=index, query=query, **kwargs)
