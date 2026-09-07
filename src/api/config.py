"""Coldline.

===================

File:              src/api/config.py
Component:         API — Config
Purpose:           Own and validate every API environment read.
Interacts With:    FastAPI, domain, ports, and adapters
Sprint/Task:       Sprint 2 — Project 2
Concepts:          HTTP boundary, composition, configuration ownership
Tools:             Python 3.12, Redis, PostgreSQL, LocalStack, Pydantic
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Describe the protected runtime configuration for the API service.

    This module is the only place in the API runtime that reads the
    environment. The composition root validates it once and passes values
    inward, so no route, use case, or adapter reaches for a variable itself.

    The object-storage credentials below are LocalStack development values.
    They are not secrets, they grant nothing outside this local Compose
    network, and they must never be replaced with a real account credential in
    this repository. Managed deployments supply credentials through their own
    protected configuration.
    """

    model_config = SettingsConfigDict(env_prefix="COLDLINE_", extra="forbid")

    database_url: str = Field(min_length=1)
    redis_url: str = Field(min_length=1)
    otel_endpoint: str = Field(min_length=1)
    service_name: str = "coldline-api"
    stream_name: str = "coldline.exception.jobs"
    consumer_group: str = "coldline-workers"

    s3_endpoint: str = Field(min_length=1)
    s3_bucket: str = Field(default="coldline-corpus", min_length=3, max_length=63)
    s3_region: str = Field(default="us-east-1", min_length=2)
    s3_access_key_id: str = Field(default="localstack-development-key", min_length=1)
    s3_secret_access_key: str = Field(default="localstack-development-secret", min_length=1)

    # Supplied retrieval defaults for Tasks 2.1 through 2.6. Task 2.7 adds one
    # bounded student-editable override file for exactly these two values.
    retrieval_top_k: int = Field(default=3, ge=1, le=50)
    retrieval_dense_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    retrieval_token_budget: int = Field(default=320, ge=32, le=4_000)
