"""Thin httpx wrapper for the Backlog REST API.

No official Python SDK exists — this is a ~100-line wrapper that covers
only the endpoints used by Context-Hub v1.0.

Real credentials (BACKLOG_API_KEY / BACKLOG_SPACE_KEY) are only on company PC.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


class BacklogClient:
    """Async HTTP client for the Backlog v2 API."""

    _MAX_COUNT = 100           # Backlog's maximum per-page count
    _RETRY_DELAYS = (1, 2, 4)  # exponential backoff in seconds

    def __init__(self, space_key: str, api_key: str) -> None:
        self._base_url = f"https://{space_key}.backlog.com/api/v2"
        self._api_key = api_key

    async def get_issues(
        self,
        project_id: int,
        updated_since: str | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch a page of issues.

        Args:
            project_id: Numeric Backlog project ID.
            updated_since: ISO 8601 string; if given, only issues updated after
                           this date are returned.
            offset: Pagination offset.
        """
        params: dict[str, Any] = {
            "projectId[]": project_id,
            "count": self._MAX_COUNT,
            "offset": offset,
        }
        if updated_since:
            params["updatedSince"] = updated_since

        return await self._get("/issues", params=params)

    async def get_issue_comments(self, issue_id: int) -> list[dict[str, Any]]:
        return await self._get(f"/issues/{issue_id}/comments")

    async def get_wikis(self, project_id_or_key: str | int) -> list[dict[str, Any]]:
        return await self._get("/wikis", params={"projectIdOrKey": project_id_or_key})

    async def get_wiki(self, wiki_id: int) -> dict[str, Any]:
        result = await self._get(f"/wikis/{wiki_id}")
        return result  # type: ignore[return-value]

    async def get_project(self, project_id_or_key: str | int) -> dict[str, Any]:
        result = await self._get(f"/projects/{project_id_or_key}")
        return result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = self._base_url + path
        all_params: dict[str, Any] = {"apiKey": self._api_key}
        if params:
            all_params.update(params)

        for attempt, delay in enumerate((*self._RETRY_DELAYS, None)):
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    response = await client.get(url, params=all_params)
                    if response.status_code == 429:
                        if delay is not None:
                            await asyncio.sleep(delay)
                            continue
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError:
                    if delay is not None:
                        await asyncio.sleep(delay)
                        continue
                    raise
        raise RuntimeError(f"Backlog API request to {path} failed after retries")
