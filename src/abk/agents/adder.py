"""Adder Agent: recipe link -> transcript -> structured recipe -> recipe book."""
from __future__ import annotations

from typing import Optional

from ..domain import Recipe, RecipeExtractionError, Role, TranscriptUnavailable
from ..llm import LLMClient
from ..services.messaging import Messenger
from ..services.recipe_book import RecipeBook
from ..services.transcription import Transcriber


class AdderAgent:
    def __init__(self, transcriber: Transcriber, llm: LLMClient,
                 recipe_book: RecipeBook, messenger: Messenger) -> None:
        self.transcriber = transcriber
        self.llm = llm
        self.recipe_book = recipe_book
        self.messenger = messenger

    def handle(self, url: str) -> Optional[Recipe]:
        try:
            transcript = self.transcriber.fetch(url)
            recipe = self.llm.extract_recipe(transcript, url)
        except TranscriptUnavailable:
            self.messenger.send(
                f"Couldn't read a recipe from {url} — no captions/transcript. Try another link.",
                to=Role.OWNER)
            return None
        except RecipeExtractionError:
            self.messenger.send(
                f"Got the transcript but couldn't structure a recipe from {url}.",
                to=Role.OWNER)
            return None

        saved, created = self.recipe_book.add_recipe(recipe)
        if created:
            self.messenger.send(
                f"Added '{saved.name}' to the recipe book ✅ ({saved.macros.calories:g} kcal).",
                to=Role.OWNER)
        else:
            self.messenger.send(
                f"'{saved.name}' is already in the recipe book — skipped.", to=Role.OWNER)
        return saved
