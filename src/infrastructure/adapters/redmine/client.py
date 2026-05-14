"""Thin httpx wrapper for the Redmine REST API.

Uses X-Redmine-API-Key header authentication.
Covers only endpoints needed for Context-Hub v1.0.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


class RedmineClient:
    """Async HTTP client for the Redmine REST API."""

    _MAX_LIMIT = 100
    _RETRY_DELAYS = (1, 2, 4)

    def __init__(self, base_url: str, api_key: str) -> None:
        # Normalise base URL (remove trailing slash)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def get_issues(
        self,
        project_identifier: str,
        updated_on: str | None = None,
        offset: int = 0,
        include_journals: bool = True,
    ) -> dict[str, Any]:
        """Fetch a page of issues.

        Returns the full response dict (including total_count for pagination).
        """
        params: dict[str, Any] = {
            "project_id": project_identifier,
            "limit": self._MAX_LIMIT,
            "offset": offset,
        }
        if updated_on:
            # Redmine syntax: updated_on=>=<ISO 8601>
            params["updated_on"] = f">={updated_on}"
        if include_journals:
            params["include"] = "journals"

        return await self._get("/issues.json", params=params)  # type: ignore[return-value]

    async def get_issue(self, issue_id: int) -> dict[str, Any]:
        result = await self._get(
            f"/issues/{issue_id}.json",
            params={"include": "journals,attachments"},
        )
        return result  # type: ignore[return-value]

    async def get_wiki_index(self, project_identifier: str) -> list[dict[str, Any]]:
        result = await self._get(f"/projects/{project_identifier}/wiki/index.json")
        return result.get("wiki_pages", [])  # type: ignore[union-attr]

    async def get_wiki_page(
        self, project_identifier: str, title: str
    ) -> dict[str, Any]:
        result = await self._get(
            f"/projects/{project_identifier}/wiki/{title}.json"
        )
        return result.get("wiki_page", {})  # type: ignore[union-attr]

    async def get_project(self, project_identifier: str) -> dict[str, Any]:
        result = await self._get(f"/projects/{project_identifier}.json")
        return result.get("project", {})  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = self._base_url + path
        headers = {"X-Redmine-API-Key": self._api_key}

        for attempt, delay in enumerate((*self._RETRY_DELAYS, None)):
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    response = await client.get(url, params=params, headers=headers)
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
        raise RuntimeError(f"Redmine API request to {path} failed after retries")
