"""Offline end-to-end demo — a full day, no credentials needed.

Run:  python apps/demo.py
Everything the agent 'posts' to the group is printed to the console.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from abk.app import build_app  # noqa: E402
from abk.domain import Ingredient, Macros, Profile, Recipe  # noqa: E402
from abk.services.messaging import FakeMessenger  # noqa: E402
from abk.services.transcription import FakeTranscriber  # noqa: E402


def show(messenger: FakeMessenger, seen: list) -> None:
    for msg in messenger.outbox[len(seen):]:
        who = f"@{msg.to.value}" if msg.to else "group"
        print(f"    agent → {who}: " + msg.text.replace("\n", "\n        "))
    seen.clear()
    seen.extend(messenger.outbox)


def main() -> None:
    messenger = FakeMessenger()
    transcriber = FakeTranscriber({
        "https://youtu.be/PANEER12345": (
            "NAME: Palak Paneer\nMACROS: 400, 22, 18, 26\n"
            "INGREDIENTS:\n2 cup spinach\n200 g paneer\n1 unit onion\n"
            "STEPS:\nBlanch spinach\nSimmer with paneer\n"
        ),
    })
    app = build_app(messenger=messenger, transcriber=transcriber, profile=Profile(
        name="Sample User", goal="muscle gain", meals_per_day=3,
        macro_targets=Macros(2800, 165, 360, 78)))

    app.add_recipe(Recipe("Poha", Macros(300, 8, 50, 6),
                          [Ingredient("poha", 2, "cup")], ["cook"], "https://youtu.be/POHA"))
    app.add_recipe(Recipe("Dal Rice", Macros(550, 20, 90, 8),
                          [Ingredient("rice", 1, "cup")], ["cook"], "https://youtu.be/DAL"))

    owner, cook = app.settings.owner_jid, app.settings.cook_jid
    seen: list = []

    print("\n1) Owner shares a recipe link")
    app.inbound(owner, "found this https://youtu.be/PANEER12345")
    show(messenger, seen)

    print("\n2) 08:00 — daily plan proposed")
    app.conversation.start_daily("2026-07-27")
    show(messenger, seen)

    print("\n3) Owner revises (lighter)")
    app.inbound(owner, "make it lighter please")
    show(messenger, seen)

    print("\n4) Cook tries to approve (ignored — not the owner)")
    r = app.inbound(cook, "approve")
    print(f"    [router action: {r.action}]")

    print("\n5) Owner approves — cook gets the menu and is asked for the list")
    app.inbound(owner, "approve")
    show(messenger, seen)

    print("\n6) Cook sends the material list")
    app.inbound(cook, "need 200g paneer, 1 kg onion, 2 packet bread, salt")
    show(messenger, seen)

    print("\n7) Owner approves the order")
    app.inbound(owner, "approve")
    show(messenger, seen)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
