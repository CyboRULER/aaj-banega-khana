"""Profile & preferences store."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain import Profile


class ProfileStore(ABC):
    @abstractmethod
    def get(self) -> Profile: ...

    @abstractmethod
    def set(self, profile: Profile) -> None: ...


class InMemoryProfileStore(ProfileStore):
    def __init__(self, profile: Profile | None = None) -> None:
        self._profile = profile or Profile()

    def get(self) -> Profile:
        return self._profile

    def set(self, profile: Profile) -> None:
        self._profile = profile
