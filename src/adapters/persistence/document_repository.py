"""Coldline.

===================

File:              src/adapters/persistence/document_repository.py
Component:         Adapter — Document repository (student implementation)
Purpose:           Implement the application-facing document and chunk data layer.
Interacts With:    PostgreSQL, domain contracts, the document service
Sprint/Task:       Sprint 2 — Project 2 / Task 2.3
Concepts:          Repository pattern, scoped reads, parameterized SQL, transactions
Tools:             Python 3.12, PostgreSQL, asyncpg

This file is student-editable, and it is the only file inside `src/adapters/`
that any Task permits a student to change. Persistence belongs here rather than
in `domain`, because it is where a concrete driver is allowed.

Implement `PostgresDocumentRepository` against the contract in
`src/domain/repositories.py`. Read that contract first: it states the four
requirements every operation must satisfy and what each check means.

Notes that will save you time:

- The connection pool arrives through the constructor. Do not create your own
  client, and do not read the environment: `src/api/config.py` owns every
  environment read in this runtime.
- Use `$1`-style parameter placeholders for every value. The checks pass
  document titles containing quotation marks, semicolons, dashes, and non-ASCII
  characters, and a string-formatted query will either crash or change meaning.
- `domain.embedding.format_vector` turns a chunk embedding into the textual
  `vector` literal PostgreSQL expects, the same way the supplied baseline
  loader does. Bind it as a parameter and cast it in SQL with `$n::vector`.
- The `documents` and `chunks` tables already exist. The schema is in
  `infra/postgres/002_retrieval_corpus.sql`; it is protected, and Task 2.6 is
  where a schema change belongs.
- Wire your implementation by returning it from `build_document_repository` in
  `src/api/extensions/wiring.py`. Until you do, the document API answers 503
  and the application-integration check fails.
"""

from collections.abc import Sequence

import asyncpg

from domain.contracts import AuthorizationContext, ChunkRecord, DocumentRecord


class PostgresDocumentRepository:
    """Persist and read documents and chunks in PostgreSQL.

    Implements `domain.repositories.DocumentRepository`.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        """Bind the repository to one initialized connection pool."""
        self._pool = pool

    async def save_document(self, document: DocumentRecord, chunks: Sequence[ChunkRecord]) -> None:
        """Insert one document and all of its chunks in one transaction."""
        raise NotImplementedError("Task 2.3: implement the atomic document and chunk write")

    async def get_document(
        self, document_id: str, *, scope: AuthorizationContext
    ) -> DocumentRecord | None:
        """Return one document, or None when the scope may not read it."""
        raise NotImplementedError("Task 2.3: implement the scoped document read")

    async def list_documents(self, *, scope: AuthorizationContext) -> list[DocumentRecord]:
        """Return every document the scope may read, ordered by identifier."""
        raise NotImplementedError("Task 2.3: implement the scoped document listing")

    async def get_chunks(
        self, document_id: str, *, scope: AuthorizationContext
    ) -> list[ChunkRecord]:
        """Return the readable chunks of one document, ordered by chunk index."""
        raise NotImplementedError("Task 2.3: implement the scoped chunk read")
