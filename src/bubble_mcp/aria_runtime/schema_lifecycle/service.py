"""Composition root for schema lifecycle services."""

from __future__ import annotations

from .protocols import SchemaLifecycleHost
from .data_types import DataTypeLifecycleService
from .options import OptionLifecycleService
from .privacy import PrivacyLifecycleService
from .references import SchemaReferenceResolver
from .settings import SettingsLifecycleService


class SchemaLifecycleService:
    """Compose typed schema lifecycle operations over one BubbleCLI host."""

    def __init__(self, host: SchemaLifecycleHost) -> None:
        self.references = SchemaReferenceResolver(host)
        self.data_types = DataTypeLifecycleService(host, self.references)
        self.options = OptionLifecycleService(host, self.references)
        self.privacy = PrivacyLifecycleService(host, self.references)
        self.settings = SettingsLifecycleService(host, self.references)
