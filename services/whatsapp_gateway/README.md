# WhatsApp gateway (Node + Baileys)

Thin transport between the WhatsApp group and the Python core.

## Run
```bash
cd services/whatsapp_gateway
npm install
ABK_WEBHOOK_URL=http://localhost:8000/inbound \
ABK_GROUP_ID=<your-group-jid>@g.us \
npm start
```
Scan the QR once with the WhatsApp account you want to act as the agent bot.

## Endpoints
- inbound group messages → `POST {ABK_WEBHOOK_URL}` `{jid, text, group_id}`
- `POST /send` `{group_id, text, mention}` — post into the group
- `GET /health`

> Uses an unofficial library. Link a number you're comfortable risking (ToS).
