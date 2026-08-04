# Deploying to Railway

Two always-on services plus a Postgres database:

| Service | Root directory | Why it must stay running |
|---|---|---|
| `core` | `/` | webhook + 08:00 scheduler thread |
| `gateway` | `services/whatsapp_gateway` | holds a persistent WhatsApp socket |

The gateway **cannot** run on serverless platforms (Vercel, Lambda, Cloudflare
Workers). Baileys keeps a WebSocket open indefinitely and rotates session keys on
disk; request-scoped functions have neither.

## 1. Create the project

```bash
railway login
railway init            # from the repo root
railway add --database postgres
```

## 2. Core service

Root directory `/`. Railway reads [railway.json](railway.json) for the build and
start command.

| Variable | Value |
|---|---|
| `PORT` | `8000` |
| `ABK_BIND_HOST` | `::` |
| `DATABASE_URL` | reference the Postgres service |
| `ABK_GATEWAY_URL` | `http://gateway.railway.internal:8787` |

Plus the app settings from `.env.example`: `ABK_OWNER_JID`, `ABK_COOK_JID`,
`ABK_OWNER_LID`, `ABK_COOK_LID`, `ABK_GROUP_NAME`, `ABK_TIMEZONE`,
`ABK_PLAN_TIME`, `ABK_LLM_PROVIDER`, the provider API key, and the Instamart
settings if you use them.

`ABK_BIND_HOST=::` is required. Railway's private network is IPv6-only, so a
server bound to `0.0.0.0` is unreachable at `*.railway.internal`.

## 3. Gateway service

Root directory `services/whatsapp_gateway`.

| Variable | Value |
|---|---|
| `PORT` | `8787` |
| `ABK_AUTH_DIR` | `/data/auth_info` |
| `ABK_WEBHOOK_URL` | `http://core.railway.internal:8000/inbound` |
| `ABK_GROUP_NAME` | your group's name, exactly as it appears in WhatsApp |
| `ABK_QR_TOKEN` | a long random string — gates `/qr` |

**Attach a volume mounted at `/data`.** Without it the WhatsApp session is lost
on every restart and you will be re-scanning the QR forever.

Keep both services at 1 replica. WhatsApp permits one session per link, and a
second core replica would fire the daily plan twice.

## 4. Link WhatsApp (once)

The gateway prints a QR on first boot. Railway's log viewer often mangles the
block characters, so use the fallback:

```
https://<gateway-domain>/qr?token=<ABK_QR_TOKEN>
```

Scan it from the agent's phone: WhatsApp → Settings → Linked devices → Link a
device. The session then persists on the volume.

Anyone who scans that QR links the gateway to *their* WhatsApp, which is why the
endpoint is token-gated. Unset `ABK_QR_TOKEN` after linking to disable it.

## 5. Verify

```bash
curl https://<core-domain>/health              # {"ok": true, ...}
curl https://<gateway-domain>/health           # {"ok": true, "connected": true, ...}
curl https://<gateway-domain>/groups           # confirms the group resolved
```

Then post in the group — the agent replies, and posts the plan at
`ABK_PLAN_TIME`.

## Notes

- Persistence switches to Postgres whenever `ABK_DATABASE_URL` or `DATABASE_URL`
  is set; otherwise it stays on the local SQLite file. Tests are unaffected.
- The core needs no public domain — only the gateway does, and only for `/qr`.
  You can remove the core's domain once you have verified the deploy.
