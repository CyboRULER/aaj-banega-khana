"""Transcription port: recipe link -> transcript text.

Offline default is `FakeTranscriber` (canned transcripts). The live adapter uses
youtube captions and lives in abk.adapters.youtube.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain import TranscriptUnavailable


class Transcriber(ABC):
    @abstractmethod
    def fetch(self, url: str) -> str: ...


class FakeTranscriber(Transcriber):
    """Maps URLs to canned transcripts; unknown URLs raise TranscriptUnavailable."""

    def __init__(self, mapping: dict[str, str] | None = None,
                 default: str | None = None) -> None:
        self._mapping = mapping or {}
        self._default = default

    def add(self, url: str, transcript: str) -> None:
        self._mapping[url] = transcript

    def fetch(self, url: str) -> str:
        if url in self._mapping:
            return self._mapping[url]
        if self._default is not None:
            return self._default
        raise TranscriptUnavailable(f"no transcript available for {url}")
