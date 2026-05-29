"""Manual document ingestion endpoints.

POST /api/v1/documents
    Insert a single user-supplied document as JSON (meeting notes, memo, email
    body, ...). Bypasses the Slack/Backlog/Redmine adapters.

POST /api/v1/documents/upload
    Multipart upload for .md / .txt / .pdf / .docx files. The server extracts
    plain text and routes it through the same pipeline as POST /documents.
    PDF / DOCX support requires the [documents] extra.

Upsert semantics:
    Documents are keyed on (project_id, source_type, external_id) in the
    repository. Re-posting with the same external_id replaces the previous
    document (and its embedding) atomically.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from context_hub.api.dependencies import (
    get_document_repo,
    get_embedding,
    get_llm_adapter,
    get_project_repo,
)
from context_hub.api.middleware.auth import require_scope
from context_hub.api.schemas.common import ApiResponse
from context_hub.api.schemas.documents import (
    DocumentCreateRequest,
    DocumentResponse,
    UserSourceType,
)
from context_hub.domain.document.entities import Document
from context_hub.domain.document.repository import DocumentRepository
from context_hub.domain.project.repository import ProjectRepository
from context_hub.infrastructure.embedding.base import EmbeddingProvider
from context_hub.infrastructure.llm.base import LLMAdapter
from context_hub.services.document_extractor import (
    ExtractionError,
    extract,
    supported_extensions,
)
from context_hub.services.meeting_task_extractor import extract_meeting_tasks
from context_hub.shared.types import ProjectId, RawContent, Scope, SourceType, new_id

router = APIRouter(prefix="/documents", tags=["documents"])

# Reject uploads larger than 10 MiB to bound memory use during extraction.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _compose_text(title: str | None, text: str) -> str:
    if title:
        return f"# {title}\n\n{text}"
    return text


async def _save_document(
    *,
    project_id: ProjectId,
    source_type: SourceType,
    external_id: str,
    composed_text: str,
    created_at: datetime,
    source_url: str | None,
    author: str | None,
    document_repo: DocumentRepository,
    embedding: EmbeddingProvider,
    llm: LLMAdapter | None = None,
) -> Document:
    """Embed and upsert. Shared by POST / and POST /upload.

    For meeting documents, runs on-prem LLM task extraction once at ingestion
    time and persists the result on the document, so subsequent reads return a
    stable task list (a missed/drifting task is treated as a serious incident).
    """
    raw_content = RawContent(
        text=composed_text,
        source_url=source_url,
        author_id=author,
        created_at=created_at,
    )
    document = Document.create(
        project_id=project_id,
        source_type=source_type,
        external_id=external_id,
        raw_content=raw_content,
    )
    vector = await embedding.embed(composed_text)
    document = document.with_embedding(vector)

    if source_type == SourceType.MEETING and llm is not None:
        tasks = await extract_meeting_tasks(composed_text, llm)
        document = document.with_extracted_tasks(tasks)

    return await document_repo.save(document)


def _to_response(saved: Document) -> DocumentResponse:
    return DocumentResponse(
        document_id=str(saved.id),
        project_id=str(saved.project_id),
        source_type=saved.source_type.value,
        external_id=saved.external_id,
        embedded=saved.is_embedded,
        created_at=saved.created_at.isoformat(),
        updated_at=saved.updated_at.isoformat(),
    )


@router.post(
    "",
    response_model=ApiResponse[DocumentResponse],
    status_code=201,
)
async def create_document(
    request: DocumentCreateRequest,
    _consumer=Depends(require_scope(Scope.WRITE)),
    project_repo: ProjectRepository = Depends(get_project_repo),
    document_repo: DocumentRepository = Depends(get_document_repo),
    embedding: EmbeddingProvider = Depends(get_embedding),
    llm: LLMAdapter = Depends(get_llm_adapter),
) -> ApiResponse[DocumentResponse]:
    """Insert (or upsert) a user-supplied document into the project's context store."""
    project_id = ProjectId(request.project_id)
    project = await project_repo.find_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {request.project_id}")

    saved = await _save_document(
        project_id=project_id,
        source_type=SourceType(request.source_type),
        external_id=request.external_id or new_id(),
        composed_text=_compose_text(request.title, request.text),
        created_at=request.created_at or datetime.now(timezone.utc),
        source_url=request.source_url,
        author=request.author,
        document_repo=document_repo,
        embedding=embedding,
        llm=llm,
    )
    return ApiResponse.ok(_to_response(saved))


@router.post(
    "/upload",
    response_model=ApiResponse[DocumentResponse],
    status_code=201,
)
async def upload_document(
    project_id: str = Form(..., description="Target project UUID."),
    source_type: UserSourceType = Form(
        "file", description="Document classification: meeting | file | email."
    ),
    file: UploadFile = File(..., description="Upload a .md, .txt, .pdf or .docx file."),
    external_id: str | None = Form(
        None,
        description=(
            "Stable identifier for upsert deduplication. "
            "Defaults to the uploaded filename so re-uploading the same file replaces it."
        ),
    ),
    author: str | None = Form(None, description="Optional author identifier."),
    _consumer=Depends(require_scope(Scope.WRITE)),
    project_repo: ProjectRepository = Depends(get_project_repo),
    document_repo: DocumentRepository = Depends(get_document_repo),
    embedding: EmbeddingProvider = Depends(get_embedding),
    llm: LLMAdapter = Depends(get_llm_adapter),
) -> ApiResponse[DocumentResponse]:
    """Upload a document file. The server extracts text and upserts it.

    Accepted extensions: ``.md`` (Markdown), ``.txt`` (plain text), ``.pdf``,
    ``.docx``. PDF and DOCX require the optional ``[documents]`` extra to be
    installed; without it, the request returns ``400`` with installation
    instructions.
    """
    resolved_project_id = ProjectId(project_id)
    project = await project_repo.find_by_id(resolved_project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large: {len(payload)} bytes "
                f"(max {MAX_UPLOAD_BYTES} bytes)."
            ),
        )

    try:
        extracted = extract(file.filename, payload)
    except ExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    composed_text = _compose_text(extracted.title, extracted.text)
    saved = await _save_document(
        project_id=resolved_project_id,
        source_type=SourceType(source_type),
        external_id=external_id or file.filename,
        composed_text=composed_text,
        created_at=datetime.now(timezone.utc),
        source_url=None,
        author=author,
        document_repo=document_repo,
        embedding=embedding,
        llm=llm,
    )
    return ApiResponse.ok(_to_response(saved))


@router.get("/upload/supported-extensions", tags=["documents"])
async def list_supported_extensions(
    _consumer=Depends(require_scope(Scope.READ)),
) -> ApiResponse[dict[str, list[str]]]:
    """Report which file extensions the upload endpoint accepts in this install."""
    return ApiResponse.ok({"extensions": sorted(supported_extensions())})
