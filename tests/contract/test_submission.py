"""Coldline.

===================

File:              tests/contract/test_submission.py
Component:         Contract tests — Test Submission
Purpose:           Tests for the public answer and path checks for this Task's submission.
Interacts With:    Published interfaces and repository boundaries
Sprint/Task:       Sprint 2 — Project 2
Concepts:          Compatibility, ownership, export safety
Tools:             Python 3.12, pytest
"""

from pathlib import Path

import pytest
import yaml

from tests.contract.submission_validation import (
    SubmissionError,
    _load_one_document,
    main,
    validate_changed_paths,
    validate_submission,
)

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "docs/contracts/submission.schema.json"


def _task_root(tmp_path: Path, submission_text: str) -> Path:
    """Stage a minimal Task root the public verifier can validate."""
    (tmp_path / "docs/contracts").mkdir(parents=True)
    (tmp_path / "submission.yaml").write_text(submission_text, encoding="utf-8")
    (tmp_path / "submission-sample.yaml").write_text(
        (ROOT / "submission-sample.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "docs/contracts/submission.schema.json").write_text(
        SCHEMA.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def test_shipped_answer_sheet_passes_as_it_stands(tmp_path: Path) -> None:
    """Accept the shipped empty mapping, which is this Task's correct answer sheet."""
    root = _task_root(
        tmp_path, (ROOT / "tests/fixtures/submission-template.yaml").read_text(encoding="utf-8")
    )

    validate_submission(root / "submission.yaml", SCHEMA)


def test_public_entrypoint_accepts_the_shipped_sheet(tmp_path: Path) -> None:
    """The public verifier must not require an answer this Task does not ask for."""
    root = _task_root(
        tmp_path, (ROOT / "tests/fixtures/submission-template.yaml").read_text(encoding="utf-8")
    )

    assert main(root, changed_paths=[]) == 0


def test_invented_status_field_is_rejected(tmp_path: Path) -> None:
    """A self-reported status is not evidence, and the schema says so."""
    root = _task_root(tmp_path, yaml.safe_dump({"answers": {"repository_implemented": True}}))

    with pytest.raises(SubmissionError):
        validate_submission(root / "submission.yaml", SCHEMA)


def test_invented_test_report_field_is_rejected(tmp_path: Path) -> None:
    """An answer sheet is not a place to assert that tests passed."""
    root = _task_root(
        tmp_path, yaml.safe_dump({"answers": {"tests_passed": "all data layer checks green"}})
    )

    with pytest.raises(SubmissionError):
        validate_submission(root / "submission.yaml", SCHEMA)


def test_missing_answers_mapping_is_rejected(tmp_path: Path) -> None:
    """An empty mapping is required, not merely tolerated."""
    root = _task_root(tmp_path, "task: 2.3\n")

    with pytest.raises(SubmissionError, match="answers must be one mapping"):
        validate_submission(root / "submission.yaml", SCHEMA)


def test_student_editable_paths_are_permitted() -> None:
    """The advisory path gate must accept this Task's implementation surface."""
    validate_changed_paths(["submission.yaml"])
    validate_changed_paths(["src/adapters/persistence/document_repository.py"])
    validate_changed_paths(["src/api/extensions/wiring.py"])
    validate_changed_paths(["tests/student/test_my_repository.py"])

    with pytest.raises(SubmissionError, match="src/adapters/persistence/corpus_loader.py"):
        validate_changed_paths(["src/adapters/persistence/corpus_loader.py"])

    with pytest.raises(SubmissionError, match="src/domain/repositories.py"):
        validate_changed_paths(["src/domain/repositories.py"])

    with pytest.raises(SubmissionError, match="infra/postgres"):
        validate_changed_paths(["infra/postgres/002_retrieval_corpus.sql"])

    with pytest.raises(SubmissionError, match="tests/contract"):
        validate_changed_paths(["tests/contract/test_data_layer.py"])

    with pytest.raises(SubmissionError, match="src/api/document_service.py"):
        validate_changed_paths(["src/api/document_service.py"])


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "answers: {value: first, value: second}\n",
        "answers: &answer {}\n",
        "answers: *missing\n",
        "answers: {<<: {value: fictional}}\n",
        "answers: {1: fictional}\n",
    ],
    ids=["duplicate-key", "anchor", "alias", "merge-key", "non-string-key"],
)
def test_non_json_yaml_constructs_are_rejected(tmp_path: Path, unsafe_text: str) -> None:
    """Reject restricted syntax before schema validation can mask a parser defect."""
    submission = tmp_path / "submission.yaml"
    submission.write_text(unsafe_text, encoding="utf-8")

    with pytest.raises(SubmissionError, match="restricted YAML"):
        _load_one_document(submission)


def test_multiple_yaml_documents_are_rejected(tmp_path: Path) -> None:
    """A second document cannot supply or replace the answer mapping."""
    submission = tmp_path / "submission.yaml"
    submission.write_text("answers: {}\n---\nanswers: {}\n", encoding="utf-8")

    with pytest.raises(SubmissionError, match="exactly one YAML mapping"):
        _load_one_document(submission)
