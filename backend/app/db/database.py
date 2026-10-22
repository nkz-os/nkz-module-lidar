"""Database module — deprecated after Orion-LD refactor (2026-04-08)."""
# All runtime state (jobs, assets, layers) now lives in Orion-LD entities.
# This module is kept as a no-op for package import compatibility.

from sqlalchemy.orm import declarative_base

Base = declarative_base()
