"""Coldline.

===================

File:              src/api/extensions/wiring.py
Component:         API — Student service wiring
Purpose:           Decide which student implementation the application uses.
Interacts With:    api/bootstrap.py, the document repository, domain services
Sprint/Task:       Sprint 2 — Project 2 / Task 2.3
Concepts:          Composition, dependency injection, bounded student surface
Tools:             Python 3.12, PostgreSQL

This file is student-editable, and it is where the application decides which
implementation of a student-owned collaborator it uses.

Task 2.2's service boundary is settled: the reference orchestration service is
now supplied at `src/api/retrieval_orchestration.py`, and this file wires it
without a choice to make.

Task 2.3's factory is `build_document_repository`. It returns `None` in the
starter, which is why the document API answers 503 and the
application-integration check fails until you return your implementation.
"""

import asyncpg

from api.retrieval_orchestration import RetrievalOrchestrationService
from domain.repositories import DocumentRepository
from domain.services import RetrievalOrchestrator
from ports import Retriever


def build_retrieval_orchestrator(
    retriever: Retriever,
    *,
    top_k: int,
    dense_weight: float,
    citation_limit: int,
) -> RetrievalOrchestrator:
    """Return the supplied reference retrieval-orchestration service."""
    return RetrievalOrchestrationService(
        retriever,
        top_k=top_k,
        dense_weight=dense_weight,
        citation_limit=citation_limit,
    )


def build_document_repository(pool: asyncpg.Pool) -> DocumentRepository | None:
    """Return the document repository the application should use.

    Return your `PostgresDocumentRepository` from
    `src/adapters/persistence/document_repository.py`, constructed with the
    `pool` this factory receives. Do not create a second pool or a second
    client: one pool per process is the whole point of receiving it here.

    Returning `None` keeps the document API disabled, which is the starter
    state.
    """
    return None
