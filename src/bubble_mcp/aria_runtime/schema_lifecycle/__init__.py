"""Typed schema discovery and reference resolution services."""

from .references import SchemaReferenceResolver
from .service import SchemaLifecycleService

__all__ = ["SchemaLifecycleService", "SchemaReferenceResolver"]
