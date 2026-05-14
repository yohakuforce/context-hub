"""Free-form hybrid search endpoint.

POST /api/v1/query
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.middleware.auth import require_scope
from src.api.schemas.common import ApiResponse
from src.api.schemas.query import QueryRequest, QueryResponse
from src.shared.types import Scope

router = APIRouter(tags=["query"])


@router.post("/query", response_model=ApiResponse[QueryResponse])
async def execute_query(
    request: QueryRequest,
    _consumer=Depends(require_scope(Scope.READ)),
) -> ApiResponse[QueryResponse]:
    """Execute a hybrid vector + keyword search across project context.

    Returns up to `top_k` most relevant Documents/Issues.
    """
    # TODO: wire to QueryService (embedding + pgvector similarity search)
    raise HTTPException(status_code=501, detail="Not yet implemented")
