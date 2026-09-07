"""Coldline.

===================

File:              src/worker/config.py
Component:         Worker — Config
Purpose:           Own and validate every worker environment read.
Interacts With:    Redis Streams, domain, ports, and adapters
Sprint/Task:       Sprint 1 — Project 1
Concepts:          Background processing, retries, idempotency
Tools:             Python 3.12, Redis, Pydantic
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Describe the protected runtime configuration for the worker service."""

    model_config = SettingsConfigDict(env_prefix="COLDLINE_", extra="forbid")

    database_url: str = Field(min_length=1)
    redis_url: str = Field(min_length=1)
    otel_endpoint: str = Field(min_length=1)
    service_name: str = "coldline-worker"
    stream_name: str = "coldline.exception.jobs"
    consumer_group: str = "coldline-workers"
    consumer_name: str = "worker-1"
    maximum_attempts: int = Field(default=3, ge=1, le=3)
    stale_message_ms: int = Field(default=30_000, ge=1_000)
    model_latency_ms: int = Field(default=250, ge=0, le=10_000)
    metrics_port: int = Field(default=9100, ge=1024, le=65535)
