"""Coldline.

===================

File:              tests/unit/test_bootstrap.py
Component:         Unit tests — Bootstrap
Purpose:           Keep the pinned uv bootstrap re-runnable without network access.
Interacts With:    infra/scripts/bootstrap.py
Sprint/Task:       Sprint 1 — Project 1
Concepts:          Reproducibility, idempotency, version parsing
Tools:             Python 3.12, pytest
"""

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

BOOTSTRAP_PATH = Path(__file__).resolve().parents[2] / "infra/scripts/bootstrap.py"
SPEC = importlib.util.spec_from_file_location("coldline_bootstrap", BOOTSTRAP_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("bootstrap module could not be loaded")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def test_uv_version_parser_ignores_build_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recognize the pinned version even when uv prints build metadata."""
    result = SimpleNamespace(stdout="uv 0.11.8 (0e961dd9a 2026-04-27)\n")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)

    assert bootstrap._version(Path("uv")) == bootstrap.UV_VERSION


def test_bootstrap_covers_every_supported_student_platform() -> None:
    """Keep every documented host platform resolvable to a pinned uv artifact."""
    assert set(bootstrap.ARTIFACTS) == {
        ("Darwin", "arm64"),
        ("Darwin", "x86_64"),
        ("Windows", "AMD64"),
        ("Linux", "x86_64"),
        ("Linux", "aarch64"),
    }


def test_bootstrap_pins_one_authenticated_artifact_for_each_platform() -> None:
    """Every platform must name a distinct archive with a full SHA-256 digest."""
    artifacts = [artifact for artifact, _ in bootstrap.ARTIFACTS.values()]
    digests = [digest for _, digest in bootstrap.ARTIFACTS.values()]

    assert len(set(artifacts)) == len(artifacts)
    assert len(set(digests)) == len(digests)
    assert all(len(digest) == 64 and set(digest) <= set("0123456789abcdef") for digest in digests)


def test_macos_bootstrap_installs_an_extension_free_executable() -> None:
    """Take the POSIX tarball path on macOS, not the Windows zip and .exe path."""
    for machine in ("arm64", "x86_64"):
        artifact, _ = bootstrap.ARTIFACTS[("Darwin", machine)]
        assert artifact.endswith("-apple-darwin.tar.gz")
    assert ".exe" not in "".join(artifact for artifact, _ in bootstrap.ARTIFACTS.values())
