"""Coldline.

===================

File:              tests/contract/test_data_layer.py
Component:         Contract tests — Data layer
Purpose:           Run the data-layer contracts and prove the application uses them.
Interacts With:    Docker Compose, PostgreSQL, the running API
Sprint/Task:       Sprint 2 — Project 2 / Task 2.3
Concepts:          Real persistence, scoped reads, atomic writes, application integration
Tools:             Python 3.12, pytest, Docker Compose, httpx
"""

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from tests.runtime_config import host_port

TASK_ROOT = Path(__file__).resolve().parents[2]
# Assessed: a fresh starter has an unimplemented repository and is supposed to
# fail these. Runtime: they need real PostgreSQL and the running API.
pytestmark = [pytest.mark.runtime, pytest.mark.assessed]

COMPOSE = (
    "docker",
    "compose",
    "--profile",
    "observability",
    "--profile",
    "localstack",
)
TENANT = "tenant-integration"
OTHER_TENANT = "tenant-integration-other"


def _api() -> str:
    """Return the API base URL, honoring the documented host-port override."""
    return f"http://localhost:{host_port('COLDLINE_API_HOST_PORT', 8000)}"


def _payload(document_id: str, *, tenant_id: str = TENANT, tier: str = "standard") -> dict:
    """Return one document payload the API accepts."""
    return {
        "document_id": document_id,
        "title": "Integration procedure",
        "body": (
            "Confirm the probe reading and record the operator badge in the loading log. "
            "This body is long enough to produce more than one chunk so the write path "
            "exercises the multi-record transaction."
        ),
        "access": {"tenant_id": tenant_id, "access_tier": tier},
        "provenance": {
            "source_uri": f"s3://coldline-corpus/source/{document_id}.md",
            "custodian": "Integration check desk",
            "revision": "r2",
            "recorded_at": datetime(2026, 5, 1, tzinfo=UTC).isoformat(),
        },
    }


def _psql(statement: str) -> str:
    """Run one bounded psql statement and return its trimmed output."""
    result = subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "coldline",
            "-d",
            "coldline",
            "-tAc",
            statement,
        ],
        cwd=TASK_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def test_document_repository_satisfies_its_runtime_contracts() -> None:
    """Run the repository contracts inside the API container against real PostgreSQL.

    The script is piped in on standard input so the container image needs no
    test files, exactly as the Sprint 1 adapter contract does. It builds its own
    pool and exercises committed-write visibility across connections, domain mapping,
    parameterized queries, scope before result decoding, and rollback atomicity.
    """
    verifier = (TASK_ROOT / "tests" / "contract" / "data_layer_runtime.py").read_text(
        encoding="utf-8"
    )
    result = subprocess.run(
        [*COMPOSE, "exec", "-T", "api", "python", "-"],
        cwd=TASK_ROOT,
        input=verifier,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Data layer verification passed" in result.stdout


def test_application_persists_and_reads_through_the_repository() -> None:
    """The live application path must use the composed repository, not a stand-in.

    Every assertion below is checked twice: once through the API and once
    directly in PostgreSQL. A repository that answered from memory would pass
    the first and fail the second.
    """
    document_id = f"int-{uuid4().hex[:12]}"
    other_id = f"{document_id}-other"
    try:
        with httpx.Client(timeout=30.0) as client:
            created = client.post(f"{_api()}/api/v1/documents", json=_payload(document_id))
            if created.status_code == 503:
                pytest.fail(
                    "the document API reports no composed repository: return your "
                    "implementation from build_document_repository in "
                    "src/api/extensions/wiring.py"
                )
            assert created.status_code == 201, created.text
            chunk_ids = created.json()["chunk_ids"]
            assert len(chunk_ids) >= 2, chunk_ids

            # The rows exist in PostgreSQL, not only in the response.
            assert (
                _psql(f"SELECT count(*) FROM documents WHERE document_id = '{document_id}'") == "1"
            )
            assert _psql(f"SELECT count(*) FROM chunks WHERE document_id = '{document_id}'") == str(
                len(chunk_ids)
            )
            assert (
                _psql(
                    "SELECT provenance_custodian FROM documents WHERE document_id = "
                    f"'{document_id}'"
                )
                == "Integration check desk"
            )

            fetched = client.get(
                f"{_api()}/api/v1/documents/{document_id}",
                params={"tenant_id": TENANT, "clearance": "standard"},
            )
            assert fetched.status_code == 200, fetched.text
            body = fetched.json()
            assert body["access"] == {"tenant_id": TENANT, "access_tier": "standard"}
            assert body["provenance"]["revision"] == "r2"

            chunks = client.get(
                f"{_api()}/api/v1/documents/{document_id}/chunks",
                params={"tenant_id": TENANT, "clearance": "standard"},
            )
            assert chunks.status_code == 200, chunks.text
            assert [chunk["chunk_id"] for chunk in chunks.json()["chunks"]] == chunk_ids

            # A second tenancy's document must be unreachable from this scope.
            client.post(
                f"{_api()}/api/v1/documents",
                json=_payload(other_id, tenant_id=OTHER_TENANT),
            )
            leaked = client.get(
                f"{_api()}/api/v1/documents/{other_id}",
                params={"tenant_id": TENANT, "clearance": "standard"},
            )
            assert leaked.status_code == 404, leaked.text
            listing = client.get(f"{_api()}/api/v1/documents", params={"tenant_id": TENANT})
            assert listing.status_code == 200, listing.text
            identifiers = [item["document_id"] for item in listing.json()["documents"]]
            assert document_id in identifiers
            assert other_id not in identifiers
    finally:
        for identifier in (document_id, other_id):
            _psql(f"DELETE FROM chunks WHERE document_id = '{identifier}'")
            _psql(f"DELETE FROM documents WHERE document_id = '{identifier}'")


def test_supplied_retrieval_still_reads_the_ingested_corpus() -> None:
    """The baseline loader and the retrieval adapter must stay operational."""
    corpus_documents = int(_psql("SELECT count(*) FROM documents WHERE document_id LIKE 'sop-%'"))
    assert corpus_documents > 0, "the ingested corpus is missing; run `poe ingest`"
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{_api()}/api/v1/retrieval/search",
            json={
                "query_id": "q-data-layer-regression",
                "text": "record the operator badge in the loading log",
                "authorization": {"tenant_id": "tenant-northwind", "clearance": "standard"},
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["results"], "retrieval returned nothing after the data-layer change"
