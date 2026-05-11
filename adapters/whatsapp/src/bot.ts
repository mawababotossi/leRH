/**
 * leRH — WhatsApp Bot (Baileys)
 *
 * Inspiré de l'implémentation ClawGate.
 * - fetchLatestBaileysVersion pour la compatibilité protocole
 * - Message store pour les retry de chiffrement
 * - Anti-loop via zero-width space
 * - Reconnexion automatique
 */

import { Boom } from "@hapi/boom";
import { downloadContentFromMessage } from "@whiskeysockets/baileys";
import qrcode from "qrcode-terminal";
import pino from "pino";
import { apiRequest } from "./api-client.js";

const logger = pino({
  level: "debug",
  transport: {
    target: "pino-pretty",
    options: { colorize: true, translateTime: "HH:MM:ss" },
  },
});

const AUTH_DIR = "session";
let sock: any = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 15;
const processedMessages = new Set<string>();
const messageStore = new Map<string, any>();
let connectionOpenTime = 0;
const MIN_STABLE_CONNECTION_MS = 10_000;

function normalizeJid(id: string): string {
  if (!id) return "";
  if (id.includes("@g.us") || id.includes("@lid") || id.includes("@s.whatsapp.net")) return id;
  const clean = id.replace(/\+/g, "").trim();
  return `${clean}@s.whatsapp.net`;
}

function getMessageText(msg: any): string {
  return (
    msg.message?.conversation ||
    msg.message?.extendedTextMessage?.text ||
    msg.message?.imageMessage?.caption ||
    ""
  ).trim();
}

function isVoiceMessage(msg: any): boolean {
  return !!msg.message?.audioMessage?.ptt;
}

function isDocumentMessage(msg: any): boolean {
  return !!msg.message?.documentMessage;
}

function isPDFMessage(msg: any): boolean {
  const doc = msg.message?.documentMessage;
  return !!doc && doc.mimetype === "application/pdf";
}

async function sendPresence(jid: string): Promise<void> {
  if (!sock) return;
  try {
    await sock.presenceSubscribe(jid);
    await sock.sendPresenceUpdate("composing", jid);
  } catch {
    /* ignore */
  }
}

async function handleMessage(msg: any): Promise<void> {
  if (!msg.message) return;

  // Anti-loop: ignorer nos propres messages (sauf self-chat via @lid)
  if (msg.key?.fromMe && !msg.key?.remoteJid?.endsWith("@lid")) return;

  const msgId = msg.key?.id;
  if (!msgId || processedMessages.has(msgId)) return;
  processedMessages.add(msgId);

  const jid: string = msg.key?.remoteJid ?? "";
  if (!jid) return;

  const textBody = getMessageText(msg);
  const isVoice = isVoiceMessage(msg);

  // Anti-loop: ignorer les messages qu'on a envoyés (marqués par zero-width space)
  if (textBody.endsWith("\u200B")) return;

  const isDoc = isDocumentMessage(msg);
  const isPDF = isPDFMessage(msg);
  logger.info({ jid, text: textBody.slice(0, 60), isVoice, isDoc, isPDF }, "Incoming message");

  await sendPresence(jid);

  try {
    if (isDoc && isPDF) {
      const stream = await downloadContentFromMessage(msg.message.documentMessage, "document");
      const chunks: Buffer[] = [];
      for await (const chunk of stream) chunks.push(chunk);
      const buffer = Buffer.concat(chunks);
      const base64 = buffer.toString("base64");

      const result = await apiRequest<{ reply: string }>("/api/whatsapp/document", {
        method: "POST",
        body: JSON.stringify({
          from: jid,
          document_base64: base64,
          mimetype: msg.message?.documentMessage?.mimetype || "application/pdf",
          filename: msg.message?.documentMessage?.fileName || "cv.pdf",
        }),
      });

      const replyText = result.reply + "\u200B";
      const sent = await sock.sendMessage(jid, { text: replyText });
      if (sent?.key?.id && sent?.message) messageStore.set(sent.key.id, sent.message);
    } else if (isDoc) {
      // Document non-PDF
      const sent = await sock.sendMessage(jid, {
        text: "Veuillez envoyer votre CV au format PDF.\u200B",
      });
      if (sent?.key?.id && sent?.message) messageStore.set(sent.key.id, sent.message);
    } else if (isVoice) {
      const stream = await downloadContentFromMessage(msg.message.audioMessage, "audio");
      const chunks: Buffer[] = [];
      for await (const chunk of stream) chunks.push(chunk);
      const buffer = Buffer.concat(chunks);
      const base64 = buffer.toString("base64");

      const result = await apiRequest<{ reply: string }>("/api/whatsapp/voice", {
        method: "POST",
        body: JSON.stringify({
          from: jid,
          audio_base64: base64,
          mimetype: msg.message?.audioMessage?.mimetype || "audio/ogg",
        }),
      });

      const replyText = result.reply + "\u200B";
      const sent = await sock.sendMessage(jid, { text: replyText });
      if (sent?.key?.id && sent?.message) messageStore.set(sent.key.id, sent.message);
    } else if (textBody) {
      const endpoint = textBody.startsWith("/start") ? "/api/whatsapp/start" : "/api/whatsapp/message";
      logger.info({ endpoint }, "Calling API");
      try {
        const result = await apiRequest<{ reply: string }>(endpoint, {
          method: "POST",
          body: JSON.stringify({ from: jid, text: textBody }),
        });
        logger.info("API response: %d chars", result.reply?.length || 0);

        const replyText = result.reply + "\u200B";
        const sent = await sock.sendMessage(jid, { text: replyText });
        logger.info({ sentId: sent?.key?.id }, "Message sent");
        if (sent?.key?.id && sent?.message) messageStore.set(sent.key.id, sent.message);
      } catch (apiErr: any) {
        logger.error({ err: apiErr?.message || apiErr }, "API call failed");
      }

      // Nettoyer le store
      if (messageStore.size > 500) {
        const firstKey = messageStore.keys().next().value;
        if (firstKey) messageStore.delete(firstKey);
      }
    }

    try {
      await sock.sendPresenceUpdate("paused", jid);
    } catch {
      /* ignore */
    }
  } catch (err) {
    logger.error({ err }, "Error handling message");
    try {
      const errText = "Désolé, une erreur s'est produite. Veuillez réessayer.\u200B";
      const sent = await sock.sendMessage(jid, { text: errText });
      if (sent?.key?.id && sent?.message) messageStore.set(sent.key.id, sent.message);
    } catch {
      /* ignore */
    }
  }
}

async function connectToWhatsApp(): Promise<void> {
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    logger.error("Trop de tentatives de reconnexion. Arrêt.");
    process.exit(1);
  }

  // Import dynamique de Baileys (évite les souciBaileys CJS/ESM)
  const baileys: any = await import("@whiskeysockets/baileys");
  const makeWASocket = baileys.makeWASocket || baileys.default;
  const useMultiFileAuthState = baileys.useMultiFileAuthState || baileys.default?.useMultiFileAuthState;
  const DisconnectReason = baileys.DisconnectReason;

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  // Version stable (bundled avec Baileys) — éviter les dernières versions
  // qui causent des timeout sur les queries et bloquent la réception
  const version: [number, number, number] = [2, 2403, 2];
  logger.info({ version }, "Initialisation du bot WhatsApp leRH...");

  sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: true,
    syncFullHistory: false,
    fireInitQueries: true,
    browser: ["leRH", "Chrome", "0.1.0"],
    markOnlineOnConnect: true,
    shouldIgnoreJid: () => false,
    getMessage: async (key: any) => {
      return messageStore.get(key.id);
    },
  });

  sock.ev.on("creds.update", saveCreds);
  processedMessages.clear();

  // Log tous les événements pour debug
  sock.ev.on("messaging-history.set", (data: any) => {
    logger.info({ chats: data?.chats?.length, messages: data?.messages?.length }, "messaging-history.set");
  });
  sock.ev.on("messages.update", (updates: any) => {
    if (updates?.length) logger.info({ count: updates.length }, "messages.update");
  });
  sock.ev.on("message-receipt.update", (updates: any) => {
    if (updates?.length) logger.debug({ count: updates.length }, "message-receipt.update");
  });

  // Surveiller les données brutes WebSocket pour debug
  sock.ws?.on?.("message", (data: any) => {
    const raw = Buffer.isBuffer(data) ? data : Buffer.from(data || "");
    if (raw.length > 0) {
      logger.info({ len: raw.length, hex: raw.slice(0, 4).toString("hex") }, "WS raw message");
    }
  });

  sock.ev.on("connection.update", (update: any) => {
    const { connection, lastDisconnect, qr, isNewLogin } = update;

    if (qr) {
      console.log("\n📱 Scannez ce QR code avec WhatsApp:\n");
      qrcode.generate(qr, { small: true });
      console.log("\n");
    }

    if (connection === "open") {
      logger.info({ isNewLogin }, "✅ WhatsApp connecté");
      connectionOpenTime = Date.now();
      try {
        sock.sendPresenceUpdate("available");
      } catch {
        /* ignore */
      }
      // Démarrer le poller de messages en attente
      pollPendingMessages().catch((err) => logger.error({ err }, "Initial poll failed"));
      setInterval(() => pollPendingMessages().catch((err) => logger.error({ err }, "Poll error")), 10_000);
    }

    if (connection === "close") {
      const err = lastDisconnect?.error as Boom | undefined;
      const code = err?.output?.statusCode;
      const loggedOut = code === DisconnectReason?.loggedOut;
      const isConflict = err?.data?.type === "replaced";

      // Réinitialiser le compteur SEULEMENT si la connexion a été stable
      if (Date.now() - connectionOpenTime > MIN_STABLE_CONNECTION_MS) {
        reconnectAttempts = 0;
      }

      if (isConflict) {
        logger.error("Conflit de session détecté (une autre instance utilise le même compte WhatsApp).");
        logger.error("Supprimez le dossier session/ et relancez pour rescanner le QR code.");
      } else if (loggedOut) {
        logger.error("Session expirée. Supprimez le dossier session/ et relancez.");
      }

      if (loggedOut || isConflict) {
        logger.error("Arrêt du bot — session invalide.");
        if (sock) {
          sock.end(undefined);
        }
        process.exit(1);
      }

      logger.warn({ code, loggedOut }, "❌ WhatsApp déconnecté");

      reconnectAttempts++;
      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        logger.error("Trop de tentatives de reconnexion. Arrêt.");
        process.exit(1);
      }

      const delay = Math.min(5000 * reconnectAttempts, 30000);
      logger.info(`Reconnexion dans ${delay / 1000}s (tentative ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
      setTimeout(connectToWhatsApp, delay);
    }
  });

  sock.ev.on("messages.upsert", async (event: any) => {
    try {
      const { messages, type } = event;
      logger.info({ type, count: messages.length }, "messages.upsert");

      // Log le premier message pour debug
      if (messages?.[0]) {
        const m = messages[0];
        logger.info({
          fromMe: m.key?.fromMe,
          jid: m.key?.remoteJid,
          hasMsg: !!m.message,
          type: m.message?.conversation?.slice(0, 30),
          msgId: m.key?.id,
        }, "message detail");
      }

      if (type !== "notify") return;

      for (const msg of messages) {
        await handleMessage(msg);
      }
    } catch (err) {
      logger.error({ err }, "FATAL: messages.upsert handler crashed");
    }
  });

  // Vérification périodique de la connexion
  setInterval(() => {
    const wsState = sock?.ws?.readyState;
    logger.info({ wsState, reconnectAttempts }, "Heartbeat — connection state");
  }, 30_000);
}

interface PendingMessage {
  id: number;
  message_type: string;
  text: string;
  document_path: string | null;
  platform_chat_id?: string;
}

async function pollPendingMessages(): Promise<void> {
  if (!sock) return;
  try {
    const res = await fetch(`${process.env.LERH_API_URL || "http://localhost:8000"}/api/whatsapp/pending`);
    if (!res.ok) {
      logger.warn({ status: res.status }, "Failed to fetch pending messages");
      return;
    }
    const messages: PendingMessage[] = await res.json();
    if (messages.length === 0) return;

    logger.info({ count: messages.length }, "Fetching pending messages");

    const API_URL = (process.env.LERH_API_URL || "http://localhost:8000").replace("/api", "");

    for (const msg of messages) {
      // Convert phone number to proper WhatsApp JID format
      let jid = msg.platform_chat_id || msg.id.toString();
      if (jid && !jid.includes("@")) {
        jid = `${jid}@s.whatsapp.net`;
      }

      try {
        if (msg.message_type === "document" && msg.document_path) {
          const downloadUrl = `${API_URL}/documents/download/${msg.document_path}`;
          const filename = msg.document_path.split("/").pop() || "document.docx";

          const fileRes = await fetch(downloadUrl);
          if (!fileRes.ok) {
            logger.error({ status: fileRes.status, url: downloadUrl }, "Failed to download document");
            continue;
          }
          const arrayBuffer = await fileRes.arrayBuffer();
          const buffer = Buffer.from(arrayBuffer);

          await sock.sendMessage(jid, {
            document: buffer,
            mimetype: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            fileName: filename,
            caption: msg.text,
          });
          logger.info({ id: msg.id, file: filename }, "Document sent via WhatsApp");
        } else {
          await sock.sendMessage(jid, { text: msg.text + "\u200B" });
          logger.info({ id: msg.id }, "Text message sent via WhatsApp");
        }
      } catch (err) {
        logger.error({ err, msgId: msg.id }, "Failed to send pending message");
      }
    }
  } catch (err) {
    logger.error({ err }, "Error polling pending messages");
  }
}

// Vérification que l'API est accessible
async function checkApiHealth() {
  try {
    const res = await fetch(`${process.env.LERH_API_URL || "http://localhost:8000"}/health`);
    const data = await res.json();
    logger.info({ data }, "API health check");
  } catch (err) {
    logger.warn({ err }, "API not reachable on startup");
  }
}
checkApiHealth();

// Arrêt propre
// Capturer les rejets de promesse silencieux (async event handlers)
process.on("unhandledRejection", (reason) => {
  logger.error({ err: reason }, "UNHANDLED PROMISE REJECTION");
});
process.on("uncaughtException", (err) => {
  logger.error({ err }, "UNCAUGHT EXCEPTION");
});

process.on("SIGINT", async () => {
  logger.info("Arrêt du bot WhatsApp...");
  if (sock) {
    sock.end(undefined);
  }
  process.exit(0);
});

process.on("SIGTERM", async () => {
  logger.info("SIGTERM reçu, arrêt...");
  if (sock) {
    sock.end(undefined);
  }
  process.exit(0);
});

connectToWhatsApp().catch((err) => {
  logger.fatal({ err }, "Erreur fatale du bot WhatsApp");
  process.exit(1);
});
