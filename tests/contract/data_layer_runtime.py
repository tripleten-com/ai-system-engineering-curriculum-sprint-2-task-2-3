"""Coldline.

===================

File:              tests/contract/data_layer_runtime.py
Component:         Contract tests — Data layer runtime
Purpose:           Verify the document repository against real PostgreSQL.
Interacts With:    PostgreSQL, the student repository, domain contracts
Sprint/Task:       Sprint 2 — Project 2 / Task 2.3
Concepts:          Committed-write visibility, scoped reads, parameterized SQL, atomic writes
Tools:             Python 3.12, PostgreSQL, asyncpg
"""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg

from adapters.persistence.document_repository import PostgresDocumentRepository
from domain.chunking import chunk_document
from domain.contracts import (
    AccessLabel,
    AccessTier,
    AuthorizationContext,
    ChunkRecord,
    DocumentRecord,
    Provenance,
)
from domain.embedding import embed
from domain.repositories import RepositoryError

DATABASE_URL = "postgresql://coldline:coldline_local@postgres:5432/coldline"

# One prefix per run keeps these checks from colliding with the ingested corpus
# or with a concurrent run, and makes cleanup exact.
RUN = uuid4().hex[:12]
TENANT_A = "tenant-check-a"
TENANT_B = "tenant-check-b"

# Values a string-formatted query cannot survive: an apostrophe, a statement
# terminator, a comment marker, a dollar-quote, and non-ASCII text.
ADVERSARIAL_TITLE = "O'Brien's rule; DROP TABLE documents; -- $$ Kühlkette 冷鎖"
ADVERSARIAL_BODY = (
    "Values that break string-formatted SQL: an apostrophe ' and a semicolon ; and a "
    "comment marker -- and a dollar-quote $$ and non-ASCII text Kühlkette 冷鎖. This body is "
    "long enough to split into more than one chunk so the multi-record write is exercised "
    "rather than assumed, which is the whole point of an atomic document plus chunks insert."
)
RECORDED_AT = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)


def document(
    suffix: str,
    *,
    tenant_id: str = TENANT_A,
    access_tier: AccessTier = AccessTier.STANDARD,
    title: str = "Check procedure",
    body: str = "Body one two three four five six seven eight nine ten.",
) -> DocumentRecord:
    """Return one fixture document with a full label and custody record."""
    document_id = f"chk-{RUN}-{suffix}"
    return DocumentRecord(
        document_id=document_id,
        title=title,
        body=body,
        access=AccessLabel(tenant_id=tenant_id, access_tier=access_tier),
        provenance=Provenance(
            source_uri=f"s3://coldline-corpus/source/{document_id}.md",
            custodian="Data layer check desk",
            revision="r7",
            recorded_at=RECORDED_AT,
        ),
    )


def scope(tenant_id: str, clearance: AccessTier) -> AuthorizationContext:
    """Return one caller scope."""
    return AuthorizationContext(tenant_id=tenant_id, clearance=clearance)


async def verify() -> None:
    """Verify committed-write visibility, mapping, scoped reads, and atomicity."""
    read_probe = ScopedReadProbe()
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4, init=read_probe.install)
    assert pool is not None
    repository = PostgresDocumentRepository(pool)
    try:
        await _verify_probe_controls(pool, read_probe)
        await _verify_durability_and_mapping(pool, repository)
        await _verify_parameterized_queries(pool, repository)
        await _verify_scoped_reads(repository, read_probe)
        await _verify_atomic_rollback(pool, repository)
        await _verify_no_partial_state_on_duplicate(pool, repository)
    finally:
        await _cleanup(pool)
        await pool.close()
    print(
        "Data layer verification passed: committed-write visibility across connections at "
        f"{EXPECTED_ISOLATION} isolation, mapping, scoping, and rollback atomicity are valid."
    )


# The PostgreSQL default, and the level this repository runs at: nothing in
# compose.yaml, the initialization SQL, or the pool setup changes it. The
# committed-write check below verifies this declared setup explicitly.
EXPECTED_ISOLATION = "read committed"


class ScopedReadProbe:
    """Observe denied fixture content at the driver's result-decoding boundary.

    Decoder callbacks run before fetch, prepared-statement, or cursor results
    reach repository code. Unique fixture identifiers also occur in chunk IDs
    and provenance URIs, so returning a row as JSON or renaming its columns does
    not hide it. No SQL spelling, predicate arrangement, or query plan is assumed.
    This checks the supplied fixture cases, not arbitrary data-flow obfuscation.
    """

    def __init__(self) -> None:
        """Start with no scoped operation active."""
        self._denied: tuple[str, ...] = ()
        self._leaked = False

    async def install(self, connection: asyncpg.Connection) -> None:
        """Keep normal string values while observing PostgreSQL textual results."""
        for name in ("text", "varchar", "bpchar", "json", "jsonb"):
            await connection.set_type_codec(
                name, schema="pg_catalog", encoder=str, decoder=self.decode, format="text"
            )

    def decode(self, value: str) -> str:
        """Reject denied fixture content before repository mapping or filtering."""
        if any(marker in value for marker in self._denied):
            self._leaked = True
            raise AssertionError("SQL returned out-of-scope document or chunk content")
        return value

    @contextmanager
    def denying(self, *records: DocumentRecord) -> Iterator[None]:
        """Require each awaited read to exclude these rows before driver decoding."""
        self._denied = tuple(record.document_id for record in records)
        self._leaked = False
        try:
            yield
        finally:
            self._denied = ()
            # A repository that catches a decoding error and then returns None
            # still fetched forbidden content, so that error cannot hide the leak.
            assert not self._leaked, "SQL returned out-of-scope document or chunk content"


async def _verify_probe_controls(pool: asyncpg.Pool, read_probe: ScopedReadProbe) -> None:
    """Prove the real driver's callbacks preserve allowed values and reject denied ones."""
    denied = document("decoder-negative-control")
    statements = (
        "SELECT $1::text",
        "SELECT json_build_object('document_id', $1::text)",
        "SELECT jsonb_build_object('document_id', $1::text)",
    )
    for statement in statements:
        with read_probe.denying(denied):
            assert await pool.fetchval(statement, "allowed-control") is not None
        try:
            with read_probe.denying(denied):
                await pool.fetchval(statement, denied.document_id)
        except AssertionError as error:
            assert str(error) == "SQL returned out-of-scope document or chunk content"
        else:
            raise AssertionError("the database result-decoding scope probe is not active")


async def _verify_durability_and_mapping(
    pool: asyncpg.Pool, repository: PostgresDocumentRepository
) -> None:
    """Check that a committed write is visible to a separate connection and fully mapped."""
    record = document("durable")
    chunks = chunk_document(record)
    assert len(chunks) >= 1
    await repository.save_document(record, chunks)

    # A second, independent connection. Reading the write back through the same
    # pool would also succeed inside an uncommitted transaction, which is
    # exactly the mistake this check exists to catch.
    #
    # The transaction setup on this reading side is published rather than
    # assumed, because what the check proves depends on it. This connection
    # opens no explicit transaction, so each statement below runs in its own
    # implicit one and takes a fresh snapshot; at READ COMMITTED that snapshot
    # includes every transaction committed before the statement began. So a row
    # this connection can see is a row some other connection committed.
    #
    # Assert the published setup rather than infer it. REPEATABLE READ and
    # SERIALIZABLE retain a snapshot across an explicit transaction, not across
    # the lifetime of a connection. With no explicit transaction, each statement
    # still runs in a separate transaction. This check does not test crash recovery.
    separate = await asyncpg.connect(DATABASE_URL)
    try:
        isolation = await separate.fetchval("SHOW transaction_isolation")
        assert isolation == EXPECTED_ISOLATION, (
            f"the reading connection is at {isolation!r} isolation; the published verification "
            f"setup requires {EXPECTED_ISOLATION!r}"
        )
        assert not separate.is_in_transaction(), (
            "the reading connection has an explicit transaction; this check requires each "
            "statement to run in its own implicit transaction"
        )
        row = await separate.fetchrow(
            "SELECT * FROM documents WHERE document_id = $1", record.document_id
        )
        assert row is not None, "the document is not visible to a separate connection"
        assert row["title"] == record.title
        assert row["tenant_id"] == record.access.tenant_id
        assert row["access_tier"] == record.access.access_tier.value
        assert row["provenance_custodian"] == record.provenance.custodian
        assert row["provenance_revision"] == record.provenance.revision
        assert row["provenance_source_uri"] == record.provenance.source_uri
        assert row["provenance_recorded_at"] == record.provenance.recorded_at
        stored_chunks = await separate.fetch(
            "SELECT * FROM chunks WHERE document_id = $1 ORDER BY chunk_index",
            record.document_id,
        )
        assert len(stored_chunks) == len(chunks), (
            f"{len(stored_chunks)} chunk row(s) for {len(chunks)} chunks"
        )
    finally:
        await separate.close()

    # Domain mapping in the other direction: the record that comes back must
    # carry every label and custody field, not a subset of them.
    mapped = await repository.get_document(
        record.document_id, scope=scope(TENANT_A, AccessTier.STANDARD)
    )
    assert mapped is not None, "the repository cannot read back its own write"
    assert mapped == record, f"mapping lost or changed fields: {mapped!r}"

    mapped_chunks = await repository.get_chunks(
        record.document_id, scope=scope(TENANT_A, AccessTier.STANDARD)
    )
    assert [chunk.chunk_id for chunk in mapped_chunks] == [chunk.chunk_id for chunk in chunks], (
        "chunk identity or order was not preserved"
    )
    assert all(chunk.access == record.access for chunk in mapped_chunks)
    assert all(chunk.provenance == record.provenance for chunk in mapped_chunks)
    assert all(len(chunk.embedding) == len(chunks[0].embedding) for chunk in mapped_chunks)


async def _verify_parameterized_queries(
    pool: asyncpg.Pool, repository: PostgresDocumentRepository
) -> None:
    """Adversarial text must round-trip byte for byte."""
    record = document("adversarial", title=ADVERSARIAL_TITLE, body=ADVERSARIAL_BODY)
    await repository.save_document(record, chunk_document(record))

    mapped = await repository.get_document(
        record.document_id, scope=scope(TENANT_A, AccessTier.STANDARD)
    )
    assert mapped is not None
    assert mapped.title == ADVERSARIAL_TITLE, "the title did not survive the round trip"
    assert mapped.body == record.body

    # The table the adversarial title names must still exist.
    assert await pool.fetchval("SELECT to_regclass('public.documents')") is not None

    # Reading by an adversarial identifier must find nothing rather than fail.
    absent = await repository.get_document(
        "chk-' OR 1=1 --", scope=scope(TENANT_A, AccessTier.STANDARD)
    )
    assert absent is None, "an injected predicate returned a row"


async def _verify_scoped_reads(
    repository: PostgresDocumentRepository, read_probe: ScopedReadProbe
) -> None:
    """Check scope both before row decoding and after domain mapping."""
    own = document("scope-own", tenant_id=TENANT_A)
    other = document("scope-other", tenant_id=TENANT_B)
    restricted = document("scope-restricted", tenant_id=TENANT_A, access_tier=AccessTier.RESTRICTED)
    for record in (own, other, restricted):
        await repository.save_document(record, chunk_document(record))

    standard_scope = scope(TENANT_A, AccessTier.STANDARD)
    with read_probe.denying(other, restricted):
        assert await repository.get_document(other.document_id, scope=standard_scope) is None, (
            "another tenancy's document was readable"
        )
        assert (
            await repository.get_document(restricted.document_id, scope=standard_scope) is None
        ), "a restricted document was readable by a standard caller"
        assert await repository.get_document(own.document_id, scope=standard_scope) is not None

        listed = await repository.list_documents(scope=standard_scope)
        identifiers = {record.document_id for record in listed}
        assert other.document_id not in identifiers, "listing leaked another tenancy"
        assert restricted.document_id not in identifiers, "listing leaked a restricted tier"
        assert own.document_id in identifiers
        assert [record.document_id for record in listed] == sorted(identifiers), (
            "listing is not ordered by identifier"
        )

        # Chunk reads carry the same scope. A chunk-level leak is the same leak.
        assert await repository.get_chunks(other.document_id, scope=standard_scope) == []
        assert await repository.get_chunks(restricted.document_id, scope=standard_scope) == []
        assert await repository.get_chunks(own.document_id, scope=standard_scope) != []

    cleared_scope = scope(TENANT_A, AccessTier.RESTRICTED)
    with read_probe.denying(other):
        assert (
            await repository.get_document(restricted.document_id, scope=cleared_scope) is not None
        )
        assert await repository.get_document(other.document_id, scope=cleared_scope) is None, (
            "clearance must not cross a tenancy boundary"
        )
        assert await repository.get_chunks(restricted.document_id, scope=cleared_scope) != []
        assert await repository.get_chunks(other.document_id, scope=cleared_scope) == []


async def _verify_atomic_rollback(
    pool: asyncpg.Pool, repository: PostgresDocumentRepository
) -> None:
    """Check that a failure part-way through a multi-record write leaves nothing behind."""
    record = document("rollback", body=ADVERSARIAL_BODY)
    chunks = list(chunk_document(record))
    assert len(chunks) >= 2, "the rollback fixture needs more than one chunk"

    # The last chunk carries an embedding of the wrong width. The `vector(64)`
    # column rejects it, so the failure happens after earlier rows are already
    # in the transaction.
    broken = ChunkRecord(
        chunk_id=chunks[-1].chunk_id,
        document_id=chunks[-1].document_id,
        chunk_index=chunks[-1].chunk_index,
        text=chunks[-1].text,
        embedding=embed("wrong width")[:8],
        access=chunks[-1].access,
        provenance=chunks[-1].provenance,
    )
    chunks[-1] = broken

    failed = False
    try:
        await repository.save_document(record, chunks)
    except (RepositoryError, asyncpg.PostgresError):
        failed = True
    assert failed, "a write with an invalid chunk was accepted"

    separate = await asyncpg.connect(DATABASE_URL)
    try:
        documents = await separate.fetchval(
            "SELECT count(*) FROM documents WHERE document_id = $1", record.document_id
        )
        chunk_rows = await separate.fetchval(
            "SELECT count(*) FROM chunks WHERE document_id = $1", record.document_id
        )
    finally:
        await separate.close()
    assert documents == 0, f"{documents} orphaned document row(s) survived the failed write"
    assert chunk_rows == 0, f"{chunk_rows} orphaned chunk row(s) survived the failed write"


async def _verify_no_partial_state_on_duplicate(
    pool: asyncpg.Pool, repository: PostgresDocumentRepository
) -> None:
    """Check that a conflicting rewrite does not leave the store half-updated."""
    record = document("duplicate")
    chunks = chunk_document(record)
    await repository.save_document(record, chunks)

    before = await pool.fetchval(
        "SELECT count(*) FROM chunks WHERE document_id = $1", record.document_id
    )
    changed = record.model_copy(update={"title": "Rewritten title"})
    try:
        await repository.save_document(changed, chunk_document(changed))
    except (RepositoryError, asyncpg.PostgresError):
        # Rejecting the rewrite is acceptable; leaving a mixed state is not.
        pass
    after = await pool.fetchval(
        "SELECT count(*) FROM chunks WHERE document_id = $1", record.document_id
    )
    assert after == before, f"chunk count changed from {before} to {after} on a rewrite"
    stored = await pool.fetchrow(
        "SELECT title FROM documents WHERE document_id = $1", record.document_id
    )
    assert stored is not None
    assert stored["title"] in {record.title, changed.title}, (
        "the stored title is neither the original nor the rewritten value"
    )


async def _cleanup(pool: asyncpg.Pool) -> None:
    """Remove only the rows this run created."""
    await pool.execute("DELETE FROM chunks WHERE document_id LIKE $1", f"chk-{RUN}-%")
    await pool.execute("DELETE FROM documents WHERE document_id LIKE $1", f"chk-{RUN}-%")


if __name__ == "__main__":
    asyncio.run(verify())
