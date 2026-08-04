"""Composition root: wire services, agents, orchestration into a runnable App.

Defaults to fully-offline, in-memory wiring (FakeLLM, FakeMessenger) so the whole
product runs and is testable without any credentials. Pass live adapters to go
live.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .agents.adder import AdderAgent
from .agents.diet import DietAgent
from .agents.order import OrderAgent
from .config import Settings
from .domain import Profile, Recipe
from .llm import LLMClient, build_llm
from .orchestration.conversation import Conversation
from .orchestration.router import MessageRouter
from .services.grocery import GroceryProvider, ManualListAdapter, build_provider
from .services.messaging import FakeMessenger, Messenger
from .services.profile import InMemoryProfileStore, ProfileStore
from .services.recipe_book import InMemoryRecipeRepository, MarkdownMirror, RecipeBook
from .services.transcription import FakeTranscriber, Transcriber


@dataclass
class App:
    settings: Settings
    llm: LLMClient
    messenger: Messenger
    recipe_book: RecipeBook
    profile_store: ProfileStore
    provider: GroceryProvider
    transcriber: Transcriber
    adder: AdderAgent
    diet: DietAgent
    order_agent: OrderAgent
    conversation: Conversation
    router: MessageRouter

    # convenience seeding helpers (used by the demo and tests)
    def seed_profile(self, profile: Profile) -> None:
        self.profile_store.set(profile)

    def add_recipe(self, recipe: Recipe) -> Recipe:
        saved, _ = self.recipe_book.add_recipe(recipe)
        return saved

    def inbound(self, jid: str, text: str, lid: str = ""):
        return self.router.handle_inbound(jid, text, lid)


def build_app(
    settings: Optional[Settings] = None,
    *,
    llm: Optional[LLMClient] = None,
    messenger: Optional[Messenger] = None,
    transcriber: Optional[Transcriber] = None,
    provider: Optional[GroceryProvider] = None,
    profile: Optional[Profile] = None,
    markdown_mirror: bool = False,
    persist: bool = False,
) -> App:
    settings = settings or Settings()
    llm = llm or build_llm(settings)
    messenger = messenger or FakeMessenger()
    transcriber = transcriber or FakeTranscriber()
    provider = provider or (build_provider(settings) if settings.grocery_provider else ManualListAdapter())

    mirror = MarkdownMirror(settings.recipe_dir) if markdown_mirror else None
    if persist:
        from .services.db import connect, SqliteProfileStore, SqliteRecipeRepository
        conn = connect(settings.db_path)
        recipe_book = RecipeBook(SqliteRecipeRepository(conn), mirror)
        profile_store = SqliteProfileStore(conn, profile)
    else:
        recipe_book = RecipeBook(InMemoryRecipeRepository(), mirror)
        profile_store = InMemoryProfileStore(profile)

    adder = AdderAgent(transcriber, llm, recipe_book, messenger)
    diet = DietAgent(profile_store, recipe_book, llm, messenger)
    order_agent = OrderAgent(provider, messenger)
    conversation = Conversation(diet, order_agent, adder, messenger, llm)
    router = MessageRouter(settings, llm, conversation, messenger)

    return App(
        settings=settings, llm=llm, messenger=messenger, recipe_book=recipe_book,
        profile_store=profile_store, provider=provider, transcriber=transcriber,
        adder=adder, diet=diet, order_agent=order_agent,
        conversation=conversation, router=router,
    )
