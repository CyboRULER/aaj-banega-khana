# Aaj Banega Khana — Architecture

A single-user, WhatsApp-group-operated multi-agent system that plans daily meals,
sends cooking instructions to a human cook, and orders missing groceries.

The WhatsApp group (you + cook + agent bot) is the entire user interface.

---

## 1. High-level shape

```
WhatsApp group  ──►  Node gateway (Baileys)  ──►  Python core  ──►  services + agents
   ▲                        │                          │
   └────────────────────────┴──────────────────────────┘  (replies posted back to group)
```

- **Node WhatsApp gateway** (`services/whatsapp_gateway`) — holds the Baileys group
  session. Exposes `POST /send`; forwards inbound group messages to the Python core
  via webhook. The only component that knows about WhatsApp. Swappable (Telegram, etc.).
- **Python core** — all logic. Hexagonal (ports & adapters): agents depend on service
  *interfaces*, never concrete clients.

---

## 2. Components

### Agents (`src/abk/agents/`)
- **Adder Agent** — recipe link (YouTube/Instagram) → transcript → structured recipe
  → recipe book.
- **Diet Agent** — Profile + Recipe Book → full-day meal plan (B/L/D + macro totals)
  → owner approval → revise loop.
- **Order Agent** — cook sends a material list → parsed into items → owner approval
  → place order via a `GroceryProvider`. (No inventory/plan-diffing.)

### Services (`src/abk/services/`, each an interface + adapter)
- `transcription` — captions-first (`youtube-transcript-api`) → Claude structures the
  recipe. Hosted transcription API as fallback. No local Whisper / ffmpeg.
- `recipe_book` — repository over SQLite (SQLAlchemy) + a markdown mirror ("its directory").
- `profile` — dietary goals, preferences, macro targets.
- `grocery` — `GroceryProvider` port with adapters:
  - `ManualListAdapter` (default, build first): posts the missing-items list; owner
    orders in one tap.
  - `InstamartMCPAdapter`: Order Agent acts as an MCP client to Swiggy Instamart's
    ordering MCP server. Recommended auto-order path.
  - `ZeptoMCPAdapter` / `BlinkitAdapter`: stubs (Blinkit has no ordering API/MCP).
- `messaging` — `WhatsAppGatewayAdapter` (HTTP to the Node gateway).

### Core (`src/abk/core/`)
Config (pydantic-settings), logging, Claude client (Opus for planning, Sonnet for
extraction/intent), message router.

### Orchestration (`src/abk/orchestration/`)
LangGraph state machines for the plan approve/revise loop and the order approval loop.

### Entrypoints (`apps/`)
- `scheduler_app` — APScheduler; fires the Diet Agent daily at 08:00.

---

## 3. Data models (`src/abk/domain/`, pure, no I/O)
- `Recipe` — name, macros, ingredients[], steps[], source_link.
- `Meal` / `MealPlan` — meals for the day + macro totals + status.
- `Profile` — goals, preferences, restrictions, macro targets.
- `GroceryItem` / `GroceryOrder` — item, qty, needed-vs-in-stock, order status.

---

## 4. The three flows

**A — Add recipe (event-driven, any time)**
link in group → gateway webhook → Adder Agent → transcript → Claude structures recipe
→ recipe book (DB + markdown) → confirmation in group.

**B — Daily plan (08:00 scheduled)**
scheduler → Diet Agent (Profile + Recipe Book) → full-day plan → group for owner
approval → approve (proceed) or revise (loop with feedback).

**C — Cook + order (post-approval)**
- To cook: cooking instructions + YouTube link + a request to send the material list.
- Cook sends the material list → Order Agent parses it → owner approval →
  `GroceryProvider` places the order.

---

## 5. Group interaction model (user ↔ cook ↔ agent)

One shared group; the agent processes every inbound message in four steps.

1. **Role resolution** — gateway attaches sender JID; router maps JID → role
   (`OWNER` / `COOK` / `UNKNOWN`). UNKNOWN is ignored.
2. **Intent classification** — Claude returns a structured intent given text + role:
   `approve_plan`, `reject_plan`, `revise_plan`, `approve_order`, `reject_order`,
   `add_recipe`, `cook_feedback`, `query`, `chit_chat`/`other`.
3. **Addressing** — the agent always names its target (@owner for approvals,
   "Cook:" prefix for cooking instructions) so each human knows who must act.
4. **Authority guardrail** — only `OWNER` may approve/reject plans and orders.
   COOK messages are kitchen feedback: they can influence a flow (missing ingredient
   → re-plan or add to order) but never authorize spending or finalize a plan.

**State** — each pending decision (plan, order) is a small state machine in the DB,
driven by LangGraph, so a late "approve" resolves the correct pending step.
Approvals may be a keyword or a 👍 reaction on the agent's message.

**Edge cases** — concurrent messages queued & processed in order; ambiguous replies
("ok but no rice") → `revise_plan` with note; post-cook shortage → inventory fix +
proposed order add; unknown sender ignored+logged; a link shared mid-approval runs
`add_recipe` in parallel without disturbing the pending plan.

---

## 6. Tech stack
- Python 3.10+ core; Claude (Opus planning / Sonnet extraction+intent).
- LangGraph (approve/revise loops), SQLAlchemy + SQLite (Postgres-ready),
  pydantic-settings, APScheduler, youtube-transcript-api, httpx, pytest.
- Node 24 + Baileys (WhatsApp group gateway).

---

## 7. Repo layout
```
aaj-banega-khana/
├── services/whatsapp_gateway/   # Node + Baileys
├── apps/scheduler_app/          # Python, 08:00 trigger
├── src/abk/
│   ├── core/  domain/  agents/  orchestration/
│   └── services/{transcription,recipe_book,profile,inventory,grocery,messaging}/
├── tests/
├── config/  pyproject.toml  .env.example  docker-compose.yml
```

---

## 8. Build phases
1. Skeleton + domain models + config + DB schema (verifiable smoke test).
2. Recipe Book + Adder Agent (transcription pipeline).
3. Profile + Diet Agent (plan + revise loop), CLI-testable.
4. WhatsApp gateway + message router wiring.
5. Inventory + Order Agent + ManualListAdapter (then InstamartMCPAdapter).
6. Scheduler + end-to-end.

Each phase is runnable/testable via CLI before WhatsApp is attached.
```
