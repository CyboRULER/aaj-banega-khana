# Aaj Banega Khana

Multi-agent daily meal planning that runs over a WhatsApp group (you + cook +
agent). The agent proposes a full-day plan every morning, sends cooking
instructions to the cook, and orders missing groceries — all approved by you in
the group.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design and interaction model, and
[ROADMAP.md](ROADMAP.md) for known gaps and planned work.

## Quick start (offline, no credentials)

The entire brain runs offline with a rule-based engine and fakes — no API key,
no WhatsApp needed.

```bash
# from the project root
python apps/demo.py          # watch a full day play out in the console
python -m unittest discover  # run the edge-case test suite
```

## Layout

```
src/abk/
  domain.py            pure models, enums, errors
  config.py            env-based settings
  llm.py               LLMClient interface + offline FakeLLM
  services/            recipe_book, profile, inventory, grocery, messaging, transcription
  agents/              adder, diet, order, cook
  orchestration/       conversation (state machine) + router (role/intent/authority)
  adapters/            live Claude, YouTube, WhatsApp-gateway adapters (lazy)
  app.py               composition root (build_app)
apps/
  demo.py              offline end-to-end demo
  server.py            live backend: /inbound webhook + 08:00 scheduler
services/whatsapp_gateway/   Node + Baileys group gateway
tests/                 unittest edge-case suite
```

## Going live (WhatsApp)

**Terminal 1 — the WhatsApp gateway** (scan the QR once with the agent's phone):
```bash
cd services/whatsapp_gateway
npm install          # first time only
npm start
```
On first run it prints a QR. On the agent's phone: WhatsApp → Settings →
**Linked devices** → *Link a device* → scan. It then lists every group it can see:

```
• "Aaj Banega Khana"  ->  120363xxxxxxxxxx@g.us
```

Put that group's **name** in `.env` as `ABK_GROUP_NAME` (the gateway resolves the
ID automatically). You can also check `curl localhost:8787/groups`.

**Terminal 2 — the core:**
```bash
python3 apps/server.py
```

Then talk to the group: the agent posts the plan at `ABK_PLAN_TIME`, you reply
`approve`, the cook sends a material list, you `approve` again.

Notes
- The core auto-selects live adapters when config/keys are present, and falls back
  to the offline engine otherwise.
- Intent classification calls the LLM, so replies take ~2-3s.
- Recipes and the profile persist in SQLite (`ABK_DB_PATH`).
- Ordering uses the manual list until `ABK_INSTAMART_MCP_URL` is set; then it
  places orders through Instamart's MCP server.
```
