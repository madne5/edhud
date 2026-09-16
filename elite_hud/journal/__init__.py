"""Journal ingestion: directory discovery, rotation-safe tailing, event routing."""

from __future__ import annotations

from .watcher import JOURNAL_GLOB, JournalTailer, JournalWatcher, list_journals

__all__ = ["JOURNAL_GLOB", "JournalTailer", "JournalWatcher", "list_journals"]
