// Baileys WhatsApp group gateway.
// - Links a WhatsApp session (scan the QR once).
// - Resolves the target group by NAME (ABK_GROUP_NAME) or by JID (ABK_GROUP_ID).
// - Forwards inbound GROUP messages to the Python core webhook.
// - Exposes POST /send so the Python core can post into the group.
//
// This is a thin transport. All logic lives in the Python core.

import fs from "fs";
import path from "path";
import express from "express";
import pino from "pino";
import qrcode from "qrcode-terminal";
import makeWASocket, {
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  Browsers,
  DisconnectReason,
} from "@whiskeysockets/baileys";

// Load ../../.env so the gateway and the Python core share one config file.
function loadEnv() {
  const envPath = path.resolve(process.cwd(), "../../.env");
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, "utf-8").split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith("#") || !t.includes("=")) continue;
    const i = t.indexOf("=");
    const k = t.slice(0, i).trim();
    const v = t.slice(i + 1).trim().replace(/^['"]|['"]$/g, "");
    if (!(k in process.env)) process.env[k] = v;
  }
}
loadEnv();

const PORT = process.env.ABK_GATEWAY_PORT || 8787;
const WEBHOOK_URL = process.env.ABK_WEBHOOK_URL || "http://localhost:8000/inbound";
const GROUP_NAME = (process.env.ABK_GROUP_NAME || "").trim();

const log = pino({ level: "info", transport: { target: "pino-pretty" } });
let sock = null;
let groupId = (process.env.ABK_GROUP_ID || "").trim();
let knownGroups = [];
// WhatsApp addresses group members by LID (e.g. 2409...@lid) rather than by
// phone JID. Keep a map so the core still sees phone numbers.
let lidToPhone = {};
let participants = [];
// IDs of messages this gateway sent, so we don't treat the bot's own output as
// owner input. (The linked account is usually the owner's own number, so their
// messages arrive with fromMe=true and must still be processed.)
const sentIds = new Set();

function normalizeJid(jid) {
  // "911111111111:16@s.whatsapp.net" -> "911111111111@s.whatsapp.net"
  if (!jid) return "";
  const [user, server] = jid.split("@");
  return `${user.split(":")[0]}@${server}`;
}

async function refreshParticipants() {
  if (!groupId) return;
  try {
    const meta = await sock.groupMetadata(groupId);
    participants = meta.participants.map((p) => ({
      id: p.id, jid: p.jid, lid: p.lid, phoneNumber: p.phoneNumber, admin: p.admin,
    }));
    lidToPhone = {};
    for (const p of participants) {
      const phone = p.phoneNumber || p.jid || (p.id?.endsWith("@s.whatsapp.net") ? p.id : null);
      const lid = p.lid || (p.id?.endsWith("@lid") ? p.id : null);
      if (lid && phone) lidToPhone[lid] = phone;
    }
    log.info(`group "${meta.subject}" has ${participants.length} participant(s), ` +
             `${Object.keys(lidToPhone).length} lid->phone mapping(s)`);
  } catch (e) {
    log.error(e, "could not fetch group metadata");
  }
}

function resolveSender(m) {
  // Our own messages: the linked account is the owner.
  if (m.key.fromMe) return normalizeJid(sock?.user?.id || "");
  // Prefer the phone JID Baileys gives us; else map the LID; else pass it through.
  const alt = m.key.participantPn || m.key.participantAlt;
  if (alt && alt.endsWith("@s.whatsapp.net")) return normalizeJid(alt);
  const raw = m.key.participant || m.key.remoteJid || "";
  return normalizeJid(lidToPhone[raw] || raw);
}

async function refreshGroups() {
  try {
    const all = await sock.groupFetchAllParticipating();
    knownGroups = Object.values(all).map((g) => ({ id: g.id, subject: g.subject }));
    log.info(`found ${knownGroups.length} group(s)`);
    for (const g of knownGroups) log.info(`  • "${g.subject}"  ->  ${g.id}`);

    if (!groupId && GROUP_NAME) {
      const match = knownGroups.find(
        (g) => g.subject.trim().toLowerCase() === GROUP_NAME.toLowerCase()
      );
      if (match) {
        groupId = match.id;
        log.info(`resolved ABK_GROUP_NAME "${GROUP_NAME}" -> ${groupId}`);
      } else {
        log.warn(`no group named "${GROUP_NAME}" found. Check the list above.`);
      }
    }
    if (!groupId && !GROUP_NAME) {
      log.warn("set ABK_GROUP_NAME (or ABK_GROUP_ID) to pick a group from the list above");
    }
  } catch (e) {
    log.error(e, "could not fetch groups");
  }
}

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState("./auth_info");
  // WhatsApp rejects outdated web versions, so always use the current one.
  const { version } = await fetchLatestBaileysVersion();
  log.info(`using WhatsApp Web version ${version.join(".")}`);
  sock = makeWASocket({
    auth: state,
    version,
    browser: Browsers.macOS("Desktop"),
    printQRInTerminal: false,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (u) => {
    const { connection, lastDisconnect, qr } = u;
    if (qr) {
      log.info("scan this QR with the agent's WhatsApp (Linked devices):");
      qrcode.generate(qr, { small: true });
    }
    if (connection === "close") {
      const shouldReconnect =
        lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      log.warn({ shouldReconnect }, "connection closed");
      if (shouldReconnect) start();
    } else if (connection === "open") {
      log.info("gateway connected to WhatsApp");
      await refreshGroups();
      await refreshParticipants();
    }
  });

  sock.ev.on("messages.upsert", async ({ messages }) => {
    for (const m of messages) {
      if (!m.message) continue;
      // Skip only OUR OWN bot output; the owner's own typing must still count.
      if (m.key.fromMe && sentIds.has(m.key.id)) continue;
      const chatId = m.key.remoteJid || "";
      if (!chatId.endsWith("@g.us")) continue; // groups only
      // Fail closed: never forward until a target group is resolved, otherwise
      // an "approve" typed in ANY group would drive the agent.
      if (!groupId || chatId !== groupId) continue;
      const rawSender = m.key.participant || chatId;
      const sender = resolveSender(m);
      const text =
        m.message.conversation || m.message.extendedTextMessage?.text || "";
      if (!text) continue;
      log.info(`inbound from ${sender}${sender !== rawSender ? ` (lid ${rawSender})` : ""}: ${text}`);
      try {
        await fetch(WEBHOOK_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ jid: sender, lid: rawSender, text, group_id: chatId }),
        });
      } catch (e) {
        log.error(e, "failed to forward message to the core");
      }
    }
  });
}

const app = express();
app.use(express.json());

// List groups this account is in - use it to find your group name/ID.
app.get("/groups", (_req, res) => res.json({ groups: knownGroups, selected: groupId }));

// Who is in the target group, and how LIDs map to phone numbers.
app.get("/participants", (_req, res) => res.json({ participants, lidToPhone }));

app.post("/send", async (req, res) => {
  const { group_id, text, mention } = req.body || {};
  const target = group_id || groupId;
  if (!sock || !target) return res.status(503).json({ error: "not connected or no group" });
  const content = { text };
  if (mention) content.mentions = [mention];
  try {
    const sent = await sock.sendMessage(target, content);
    if (sent?.key?.id) {
      sentIds.add(sent.key.id);
      if (sentIds.size > 500) sentIds.delete(sentIds.values().next().value);
    }
    res.json({ ok: true });
  } catch (e) {
    log.error(e, "send failed");
    res.status(500).json({ error: String(e) });
  }
});

app.get("/health", (_req, res) =>
  res.json({ ok: true, connected: !!sock, group: groupId || null })
);

app.listen(PORT, () => log.info(`gateway HTTP on :${PORT}`));
start();
