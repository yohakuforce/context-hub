"""MockHttpClient — fixture-backed HTTP client for test/dev without real API keys.

Usage:
    client = MockHttpClient(fixture_dir=Path("tests/fixtures/slack"))
    data = await client.get("/conversations.history")

The fixture lookup maps a path (minus the first segment) to a JSON file.
If no fixture matches, raises FileNotFoundError so tests fail explicitly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MockHttpResponse:
    """Minimal response shim returned by MockHttpClient."""

    def __init__(self, data: Any, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> Any:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(
                f"MockHttpClient: simulated error status {self.status_code}"
            )


class MockHttpClient:
    """Synchronous fixture reader wrapped in an async interface.

    Args:
        fixture_map: Explicit path → fixture file mapping.
                     Keys are path fragments (e.g. "/issues" or "issues.json").
    """

    def __init__(self, fixture_map: dict[str, Path]) -> None:
        self._fixture_map = fixture_map

    async def get(self, path: str, **_kwargs: Any) -> MockHttpResponse:
        """Return the fixture JSON that matches *path*.

        Tries exact match first, then stem-only match (strips leading '/' and
        normalises).
        """
        normalised = path.lstrip("/")
        for key, fixture_path in self._fixture_map.items():
            normalised_key = key.lstrip("/")
            if normalised == normalised_key or normalised.startswith(normalised_key):
                return self._load(fixture_path)

        raise FileNotFoundError(
            f"MockHttpClient: no fixture registered for path '{path}'. "
            f"Available: {list(self._fixture_map.keys())}"
        )

    def _load(self, fixture_path: Path) -> MockHttpResponse:
        if not fixture_path.exists():
            raise FileNotFoundError(
                f"MockHttpClient: fixture file not found: {fixture_path}"
            )
        with fixture_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return MockHttpResponse(data=data, status_code=200)
