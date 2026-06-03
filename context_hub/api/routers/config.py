"""Admin configuration endpoints — read/write the editable settings (.env).

GET  /api/v1/config   — list every editable setting (secrets masked).
PUT  /api/v1/config   — apply a batch of updates to .env, then hot-reload the
                        non-restart-required values into the running process.

Both require the ADMIN scope. Values are persisted to the .env file the server
reads at startup; secrets are never returned in full.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from context_hub.api.middleware.auth import require_scope
from context_hub.api.schemas.common import ApiResponse
from context_hub.api.schemas.config import (
    ConfigFieldView,
    ConfigResponse,
    ConfigUpdateRequest,
    ConfigUpdateResult,
    SourceCheckView,
)
from context_hub.config.connection_test import check_source
from context_hub.config.editable import (
    read_config,
    reload_runtime_settings,
    write_config,
)
from context_hub.shared.types import Scope

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=ApiResponse[ConfigResponse])
async def get_config(
    _consumer=Depends(require_scope(Scope.ADMIN)),
) -> ApiResponse[ConfigResponse]:
    """Return every editable setting with its current value (secrets masked)."""
    fields = [
        ConfigFieldView(
            env=v.env,
            label=v.label,
            group=v.group,
            secret=v.secret,
            kind=v.kind,
            options=list(v.options),
            help=v.help,
            restart_required=v.restart_required,
            tag=v.tag,
            why=v.why,
            steps=list(v.steps),
            how_to_set=v.how_to_set,
            configured=v.configured,
            value=v.value,
        )
        for v in read_config()
    ]
    return ApiResponse.ok(ConfigResponse(fields=fields))


@router.put("", response_model=ApiResponse[ConfigUpdateResult])
async def update_config(
    request: ConfigUpdateRequest,
    _consumer=Depends(require_scope(Scope.ADMIN)),
) -> ApiResponse[ConfigUpdateResult]:
    """Apply updates to .env, then hot-reload non-restart-required values."""
    result = write_config(request.updates)

    reloaded = False
    if result.changed or result.cleared:
        reload_runtime_settings()
        reloaded = True

    return ApiResponse.ok(
        ConfigUpdateResult(
            changed=result.changed,
            cleared=result.cleared,
            restart_required=result.restart_required,
            rejected=result.rejected,
            reloaded=reloaded,
        )
    )


@router.post("/test/{source}", response_model=ApiResponse[SourceCheckView])
async def test_connection(
    source: str,
    _consumer=Depends(require_scope(Scope.ADMIN)),
) -> ApiResponse[SourceCheckView]:
    """Test a source's connection: readiness, plus a live ping where supported."""
    r = await check_source(source)
    return ApiResponse.ok(
        SourceCheckView(source=r.source, ok=r.ok, detail=r.detail, live=r.live)
    )
