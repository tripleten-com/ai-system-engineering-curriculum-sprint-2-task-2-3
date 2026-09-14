"""Coldline.

===================

File:              tests/unit/test_data_layer_scope_probe.py
Component:         Unit tests — Data-layer assessment
Purpose:           Reject post-fetch filtering even when public return values look scoped.
Interacts With:    The runtime scope probe and document repository contract
Sprint/Task:       Sprint 2 — Project 2 / Task 2.3
Concepts:          Database result boundary, scoped reads, assessment regression
Tools:             Python 3.12, pytest
"""

from collections.abc import Sequence
from typing import cast

import pytest

from adapters.persistence.document_repository import PostgresDocumentRepository
from domain.contracts import AuthorizationContext, ChunkRecord, DocumentRecord
from domain.repositories import readable
from tests.contract import data_layer_runtime
from tests.contract.data_layer_runtime import ScopedReadProbe, _verify_scoped_reads, document


class RepositoryDouble:
    """Model rows decoded by a driver before a repository returns domain records."""

    def __init__(self, probe: ScopedReadProbe, post_filter: str | None) -> None:
        """Select which operation fetches forbidden rows before filtering them."""
        self.probe = probe
        self.post_filter = post_filter
        self.documents: dict[str, DocumentRecord] = {}
        self.chunks: dict[str, list[ChunkRecord]] = {}

    async def save_document(self, record: DocumentRecord, chunks: Sequence[ChunkRecord]) -> None:
        """Retain domain fixtures without requiring a database in this unit test."""
        self.documents[record.document_id] = record
        self.chunks[record.document_id] = list(chunks)

    def rows(
        self,
        operation: str,
        records: Sequence[DocumentRecord | ChunkRecord],
        scope: AuthorizationContext,
    ) -> list:
        """Return identical scoped answers whether filtering happens before or after decoding."""
        visible = [
            record
            for record in records
            if readable(scope, record.access.tenant_id, record.access.access_tier)
        ]
        database_rows = records if operation == self.post_filter else visible
        for record in database_rows:
            self.probe.decode(record.document_id)
        return visible

    async def get_document(
        self, identifier: str, *, scope: AuthorizationContext
    ) -> DocumentRecord | None:
        """Model a by-identifier read with otherwise correct returned scope."""
        record = self.documents.get(identifier)
        rows = self.rows("get_document", [record] if record else [], scope)
        return rows[0] if rows else None

    async def list_documents(self, *, scope: AuthorizationContext) -> list[DocumentRecord]:
        """Model an ordered listing with otherwise correct returned scope."""
        rows = self.rows("list_documents", list(self.documents.values()), scope)
        return sorted(rows, key=lambda record: record.document_id)

    async def get_chunks(
        self, identifier: str, *, scope: AuthorizationContext
    ) -> list[ChunkRecord]:
        """Model a chunk read with otherwise correct returned scope."""
        return self.rows("get_chunks", self.chunks.get(identifier, []), scope)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get_document", "list_documents", "get_chunks"])
async def test_post_fetch_filtering_fails_despite_correct_return_values(operation: str) -> None:
    """Each repository read must constrain results before they reach its Python code."""
    probe = ScopedReadProbe()
    repository = RepositoryDouble(probe, operation)
    with pytest.raises(AssertionError, match="SQL returned out-of-scope"):
        await _verify_scoped_reads(cast(PostgresDocumentRepository, repository), probe)


@pytest.mark.asyncio
async def test_scoped_results_allow_both_tiers_for_a_cleared_caller() -> None:
    """The probe must preserve every permitted positive case and returned value."""
    probe = ScopedReadProbe()
    repository = RepositoryDouble(probe, None)
    await _verify_scoped_reads(cast(PostgresDocumentRepository, repository), probe)


def test_catching_a_decoder_error_cannot_hide_the_forbidden_read() -> None:
    """Returning None after a denied row arrived is still a post-fetch filter."""
    probe = ScopedReadProbe()
    denied = document("denied")
    with pytest.raises(AssertionError, match="SQL returned out-of-scope"):
        with probe.denying(denied):
            try:
                probe.decode(denied.document_id)
            except AssertionError:
                pass


@pytest.mark.parametrize("representation", ["{}", "{}#0000", '{{"document_id":"{}"}}'])
def test_row_projection_and_json_do_not_hide_fixture_identity(representation: str) -> None:
    """Document IDs, chunk IDs and JSON projections retain the same denied identity."""
    probe = ScopedReadProbe()
    denied = document("denied")
    with pytest.raises(AssertionError, match="SQL returned out-of-scope"):
        with probe.denying(denied):
            probe.decode(representation.format(denied.document_id))


async def test_mapping_does_not_require_scope_filtering_or_a_listing() -> None:
    """A partial reader can complete mapping before implementing SQL scope and listing."""
    repository = RepositoryDouble(ScopedReadProbe(), "get_document")
    await data_layer_runtime._verify_mapping(cast(PostgresDocumentRepository, repository))


async def test_failed_case_does_not_suppress_unrelated_results(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A broken early mapping case must still report the later scope and rollback cases."""
    visited: list[str] = []

    async def run_case(case: str) -> None:
        visited.append(case)
        if case == "mapping":
            raise AssertionError("provenance was dropped")

    monkeypatch.setattr(data_layer_runtime, "verify_case", run_case)
    with pytest.raises(AssertionError, match="verification failed: mapping"):
        await data_layer_runtime.verify()
    assert visited == list(data_layer_runtime.CASES)
    output = capsys.readouterr().out
    assert "FAIL mapping: AssertionError: provenance was dropped" in output
    assert "PASS scoped-reads" in output
    assert "PASS atomic-rollback" in output
    assert "verification passed" not in output
