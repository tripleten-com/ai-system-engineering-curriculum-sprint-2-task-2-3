"""Coldline.

===================

File:              src/adapters/model/__init__.py
Component:         Model adapters — Package exports
Purpose:           Expose active model-provider adapters.
Interacts With:    Domain contracts, ports, and local providers
Sprint/Task:       Sprint 1 — Project 1
Concepts:          Boundary translation, deterministic infrastructure
Tools:             Python 3.12
"""

from adapters.model.deterministic import DeterministicModelProvider

__all__ = ["DeterministicModelProvider"]
