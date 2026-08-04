# Roadmap — known gaps and future work

Everything below is *known and deliberate*, not accidental. The system works
end to end today; these are the things that would make it production-grade.

Status legend: **P1** = blocks daily use · **P2** = quality · **P3** = nice to have

---

## P1 — Always-on hosting

**Problem.** The Node gateway and the Python core both run in terminals on a
MacBook. If the laptop sleeps, the terminals close, or the machine restarts,
the 08:00 meal plan never fires and inbound WhatsApp messages are dropped.

**Options.**
1. *Stopgap:* `caffeinate -dimsu python3 apps/server.py` to stop the Mac
   sleeping, plus a launchd job to restart both services on boot.
2. *Proper:* a small always-on VM (~₹400/month). Needs items below first:
   - webhook authentication (see P1 "Webhook auth")
   - the Baileys session (`auth_info/`) copied to the server
   - process supervision (systemd / pm2) for auto-restart

## P1 — Webhook authentication

`POST /inbound` on the core is unauthenticated. That is fine while everything
is on `localhost`, but the moment the core is exposed to a network, anyone who
can reach it can impersonate the owner and approve orders. Add a shared secret
header between the gateway and the core before hosting.

---

## P2 — Hitting macro targets

**Problem.** The profile targets 2800 kcal / 165 g protein, but generated plans
land around 2000–2200 kcal. Two causes:

1. **No portion scaling.** Each recipe carries fixed macros; the planner cannot
   say "1.5 servings of dal rice". Adding a `servings` multiplier per meal would
   let it reach a calorie/protein target with a small recipe book.
2. **Small recipe library.** With ~7 recipes there is little to optimise over.

**Also worth adding:** validate the generated plan against the targets and
retry/adjust if it is more than ~10% off, instead of accepting the first answer.

## P2 — Recipe library growth

Plan quality is bounded by the recipe book. Keep sharing links in the group.
Possible additions: bulk-import a channel/playlist, or a "suggest recipes I
don't have" prompt.

## P2 — Instagram recipe links

Only YouTube is supported. Instagram sits behind a login wall, so links are
rejected. Options: a session-cookie fetcher, a third-party API, or simply
letting the user paste recipe text directly into the group.

## P2 — Recipe naming

Names come from the video title, so they can read like "Add Egg to Bread
Breakfast" instead of "Egg Bread Toast". Tighten the extraction prompt to
produce a clean dish name.

---

## P3 — Nice to have

- **Cost visibility.** Show an estimated basket total before the owner approves.
- **Leftovers / repeats.** Avoid proposing the same dish two days running.
- **Weekly view.** Plan a week at a time rather than a day.
- **Multiple cooks / households.** Roles are currently a single owner + cook pair.
- **Metrics.** Track how often plans are approved vs revised, to tune the planner.
- **Zepto / Blinkit adapters.** Zepto has a partial MCP; Blinkit has none. The
  `GroceryProvider` port is ready for them.

---

## Operational notes

- **Instamart payment is Cash on Delivery.** Orders placed through the Swiggy
  MCP support COD only — the Swiggy Money wallet is not wired into the MCP path,
  so there is nothing to top up. No money moves when the agent places an order;
  someone must be home with cash. Swiggy has signalled a future "UPI Reserve Pay"
  option — revisit this when it ships, since it changes the risk profile
  (an agent could then actually spend money unattended).

- **Rotate the xAI API key** if it has ever been shared outside `.env`.
- **Roles can be swapped** by exchanging the JID *and* LID pairs in `.env`.
- `.env`, `data/` (SQLite + tokens) and `auth_info/` (WhatsApp session) are all
  gitignored — they are credentials.
- Run `python3 apps/status.py` for a 7-point health check at any time.
