"""Messaging port: how the agent posts into the group. Addressing is explicit
so each human knows who must act."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..domain import Role


@dataclass
class SentMessage:
    text: str
    to: Optional[Role] = None  # who the message is addressed to (mention), None = group


class Messenger(ABC):
    @abstractmethod
    def send(self, text: str, to: Optional[Role] = None) -> None: ...


class FakeMessenger(Messenger):
    """Records everything sent, for tests and the offline demo."""

    def __init__(self) -> None:
        self.outbox: list[SentMessage] = []

    def send(self, text: str, to: Optional[Role] = None) -> None:
        self.outbox.append(SentMessage(text=text, to=to))

    def last(self) -> Optional[SentMessage]:
        return self.outbox[-1] if self.outbox else None

    def texts(self) -> list[str]:
        return [m.text for m in self.outbox]
