"""IngestionService — use-case layer for running ingestion jobs.

Orchestrates:
  1. Create IngestionJob → PENDING
  2. Start job → RUNNING
  3. Fetch via SourceAdapter (Slack / Backlog / Redmine)
  4. Embed documents + issues  (via EmbeddingProvider)
  5. Persist Documents, Issues, IngestionJob  (via Repositories)
  6. Complete or fail job → COMPLETED / FAILED

This service has no knowledge of HTTP or APScheduler.
It is called by both the API router and the scheduler.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.domain.document.entities import Document
from src.domain.document.repository import DocumentRepository
from src.domain.ingestion.entities import IngestionJob
from src.domain.ingestion.repository import IngestionJobRepository
from src.domain.issue.entities import Issue
from src.domain.issue.repository import IssueRepository
from src.infrastructure.adapters.base import SourceAdapter
from src.infrastructure.embedding.base import EmbeddingProvider
from src.shared.types import (
    EmbeddingVector,
    JobStatus,
    ProjectId,
    SourceType,
    SyncCursor,
    SyncError,
)

logger = logging.getLogger(__name__)


class IngestionService:
    """Orchestrates a single ingestion run for one Source.

    Args:
        adapter:              SourceAdapter for the data source.
        embedding_provider:   EmbeddingProvider to vectorise text.
        job_repo:             Repository for IngestionJob persistence.
        document_repo:        Repository for Document persistence.
        issue_repo:           Repository for Issue persistence.
        batch_size:           Number of items to embed per batch.
    """

    def __init__(
        self,
        adapter: SourceAdapter,
        embedding_provider: EmbeddingProvider,
        job_repo: IngestionJobRepository,
        document_repo: DocumentRepository,
        issue_repo: IssueRepository,
        batch_size: int = 32,
    ) -> None:
        self._adapter = adapter
        self._embedding = embedding_provider
        self._job_repo = job_repo
        self._document_repo = document_repo
        self._issue_repo = issue_repo
        self._batch_size = batch_size

    async def run(
        self,
        project_id: ProjectId,
        full_resync: bool = False,
    ) -> IngestionJob:
        """Execute one ingestion cycle and return the completed job."""
        # Retrieve last completed job to reuse its sync cursor
        last_job = await self._job_repo.find_latest_completed(
            project_id=project_id,
            source_type=self._adapter.source_type,
        )
        prior_cursor: Optional[SyncCursor] = (
            last_job.sync_cursor if last_job else None
        )

        # Create and persist the job
        job = IngestionJob.create(
            project_id=project_id,
            source_type=self._adapter.source_type,
            sync_cursor=prior_cursor,
        )
        job = await self._job_repo.save(job)

        # Transition to RUNNING
        job = job.start()
        job = await self._job_repo.save(job)

        try:
            result = await self._adapter.fetch(
                project_id=project_id,
                cursor=prior_cursor,
                full_resync=full_resync,
            )
        except Exception as exc:
            logger.exception("Adapter fetch failed: %s", exc)
            error = SyncError(
                item_id="__adapter__",
                message=str(exc),
                occurred_at=__import__("datetime").datetime.utcnow(),
            )
            job = job.fail([error])
            job = await self._job_repo.save(job)
            return job

        items_processed = 0
        item_errors: list[SyncError] = []

        # --- Embed + persist Documents ---
        for doc_batch in _batched(result.documents, self._batch_size):
            embedded_docs, errs = await self._embed_documents(doc_batch)
            item_errors.extend(errs)
            for doc in embedded_docs:
                await self._document_repo.save(doc)
                items_processed += 1

        # --- Embed + persist Issues ---
        for issue_batch in _batched(result.issues, self._batch_size):
            embedded_issues, errs = await self._embed_issues(issue_batch)
            item_errors.extend(errs)
            for issue in embedded_issues:
                await self._issue_repo.save(issue)
                items_processed += 1

        # Record per-item errors (best-effort: job still COMPLETED)
        for err in item_errors:
            job = job.record_item_error(err)

        job = job.complete(
            items_processed=items_processed,
            new_cursor=result.new_cursor,
        )
        job = await self._job_repo.save(job)
        return job

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    async def _embed_documents(
        self,
        docs: list[Document],
    ) -> tuple[list[Document], list[SyncError]]:
        texts = [d.raw_content.text for d in docs]
        embedded: list[Document] = []
        errors: list[SyncError] = []

        try:
            vectors: list[EmbeddingVector] = await self._embedding.embed_batch(texts)
            for doc, vec in zip(docs, vectors):
                embedded.append(doc.with_embedding(vec))
        except Exception as exc:
            logger.warning("Embedding batch failed; falling back per-item: %s", exc)
            for doc in docs:
                try:
                    vec = await self._embedding.embed(doc.raw_content.text)
                    embedded.append(doc.with_embedding(vec))
                except Exception as item_exc:
                    errors.append(
                        SyncError(
                            item_id=str(doc.id),
                            message=str(item_exc),
                            occurred_at=__import__("datetime").datetime.utcnow(),
                        )
                    )
                    embedded.append(doc)  # persist without embedding

        return embedded, errors

    async def _embed_issues(
        self,
        issues: list[Issue],
    ) -> tuple[list[Issue], list[SyncError]]:
        texts = [f"{i.title}\n{i.description}" for i in issues]
        embedded: list[Issue] = []
        errors: list[SyncError] = []

        try:
            vectors: list[EmbeddingVector] = await self._embedding.embed_batch(texts)
            for issue, vec in zip(issues, vectors):
                embedded.append(issue.with_embedding(vec))
        except Exception as exc:
            logger.warning(
                "Embedding batch failed for issues; falling back per-item: %s", exc
            )
            for issue in issues:
                try:
                    text = f"{issue.title}\n{issue.description}"
                    vec = await self._embedding.embed(text)
                    embedded.append(issue.with_embedding(vec))
                except Exception as item_exc:
                    errors.append(
                        SyncError(
                            item_id=str(issue.id),
                            message=str(item_exc),
                            occurred_at=__import__("datetime").datetime.utcnow(),
                        )
                    )
                    embedded.append(issue)  # persist without embedding

        return embedded, errors


def _batched(items: list, size: int):
    """Yield successive chunks of `size` from *items*."""
    for i in range(0, len(items), size):
        yield items[i : i + size]
