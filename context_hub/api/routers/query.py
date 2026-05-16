"""Free-form hybrid search endpoint.

POST /api/v1/query
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from context_hub.api.dependencies import get_query_service
from context_hub.api.middleware.auth import require_scope
from context_hub.api.schemas.common import ApiResponse
from context_hub.api.schemas.query import QueryRequest, QueryResponse, QueryResultItem
from context_hub.application.query_service import QueryResult, QueryService
from context_hub.shared.types import ProjectId, Scope, SourceType

router = APIRouter(tags=["query"])


@router.post("/query", response_model=ApiResponse[QueryResponse])
async def execute_query(
    request: QueryRequest,
    _consumer=Depends(require_scope(Scope.READ)),
    query_service: QueryService = Depends(get_query_service),
) -> ApiResponse[QueryResponse]:
    """Execute a hybrid vector + keyword search across project context.

    Returns up to `top_k` most relevant Documents/Issues.
    """
    source_types = None
    if request.source_types:
        try:
            source_types = [SourceType(st) for st in request.source_types]
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid source_type value: {exc}",
            )

    results: list[QueryResult] = await query_service.search(
        project_id=ProjectId(request.project_id),
        query=request.query,
        top_k=request.top_k,
        source_types=source_types,
    )

    items = [
        QueryResultItem(
            document_id=str(r.document.id),
            source_type=r.document.source_type.value,
            title=r.title,
            snippet=r.snippet,
            score=r.score,
            relevance_reason="hybrid_search_rrf",
        )
        for r in results
    ]

    # Determine embedding model name from the first result (or fallback)
    embedding_model = (
        results[0].document.embedding_vector.model_name
        if results and results[0].document.embedding_vector
        else "mock-embedding-v1"
    )

    return ApiResponse.ok(
        QueryResponse(
            results=items,
            query_embedding_model=embedding_model,
        )
    )
