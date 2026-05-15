import "dotenv/config";
import { Boom } from "@hapi/boom";
import { downloadContentFromMessage, jidNormalizedUser, makeCacheableSignalKeyStore } from "@whiskeysockets/baileys";
import qrcode from "qrcode-terminal";
import pino from "pino";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { apiRequest } from "./api-client.js";

const logger = pino({
  level: "info", // Changé de 'debug' à 'trace' pour voir tous les paquets Baileys
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
const MIN_STABLE_CONNECTION_MS = 15_000;
// Cache pour mapper les ID bruts (ex: 2256...) vers leur JID complet (ex: ...@lid)
const jidMap = new Map<string, string>();

// Nettoyage periodique pour eviter la fuite memoire
const MAX_PROCESSED_IDS = 2000;
// Délai minimum après connexion avant d'envoyer des médias.
// Les init queries et la synchronisation multi-device prennent du temps.
const STABLE_DELAY_MS = 15_000;
function pruneProcessedMessages() {
  if (processedMessages.size > MAX_PROCESSED_IDS) {
    const toDelete = [...processedMessages].slice(0, processedMessages.size - MAX_PROCESSED_IDS);
    toDelete.forEach((id) => processedMessages.delete(id));
  }
}

/**
 * URL de base de l'API Python — sans slash final, sans suffixe /api.
 * Exemples valides : "http://localhost:8000" ou "http://api:8000"
 */
function getBaseUrl(): string {
  const raw = process.env.LERH_API_URL || "http://localhost:8000";
  return raw.replace(/\/api\/?$/, "").replace(/\/$/, "");
}

const BASE_URL = getBaseUrl();
logger.info({ BASE_URL }, "API base URL resolved");

// Emplacement local des documents (copie de la logique Python)
const DATA_DIR = path.resolve(process.cwd(), "..", "..", "data");
const GENERATED_DIR = path.join(DATA_DIR, "generated");

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
  } catch { /* ignore */ }
}

async function handleMessage(msg: any): Promise<void> {
  if (!msg.message) return;
  if (msg.key?.fromMe && !msg.key?.remoteJid?.endsWith("@lid")) return;

  const msgId = msg.key?.id;
  if (!msgId || processedMessages.has(msgId)) return;
  processedMessages.add(msgId);
  pruneProcessedMessages();

  const rawJid: string = msg.key?.remoteJid ?? "";
  if (!rawJid) return;
  const jid = jidNormalizedUser(rawJid);

  const textBody = getMessageText(msg);
  const isVoice = isVoiceMessage(msg);
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
      const base64 = Buffer.concat(chunks).toString("base64");

      const result = await apiRequest<{ reply: string }>("/api/whatsapp/document", {
        method: "POST",
        body: JSON.stringify({
          from: jid,
          document_base64: base64,
          mimetype: msg.message?.documentMessage?.mimetype || "application/pdf",
          filename: msg.message?.documentMessage?.fileName || "cv.pdf",
        }),
      });

      await sock.sendMessage(jid, { text: result.reply + "\u200B" });
    } else if (isDoc) {
      await sock.sendMessage(jid, { text: "Veuillez envoyer votre CV au format PDF.\u200B" });
    } else if (isVoice) {
      const stream = await downloadContentFromMessage(msg.message.audioMessage, "audio");
      const chunks: Buffer[] = [];
      for await (const chunk of stream) chunks.push(chunk);
      const base64 = Buffer.concat(chunks).toString("base64");

      const result = await apiRequest<{ reply: string }>("/api/whatsapp/voice", {
        method: "POST",
        body: JSON.stringify({
          from: jid,
          audio_base64: base64,
          mimetype: msg.message?.audioMessage?.mimetype || "audio/ogg",
        }),
      });

      await sock.sendMessage(jid, { text: result.reply + "\u200B" });
    } else if (textBody) {
      const endpoint = textBody.startsWith("/start")
        ? "/api/whatsapp/start"
        : "/api/whatsapp/message";

      const result = await apiRequest<{ reply: string }>(endpoint, {
        method: "POST",
        body: JSON.stringify({ from: jid, text: textBody }),
      });

      const sentMsg = await sock.sendMessage(jid, { text: result.reply + "\u200B" });
      if (sentMsg?.key?.id && sentMsg.message) {
        messageStore.set(sentMsg.key.id, sentMsg.message);
      }

      if (messageStore.size > 500) {
        const firstKey = messageStore.keys().next().value;
        if (firstKey) messageStore.delete(firstKey);
      }
    }

    try { await sock.sendPresenceUpdate("paused", jid); } catch { /* ignore */ }
  } catch (err) {
    logger.error({ err }, "Error handling message");
    try {
      await sock.sendMessage(jid, {
        text: "Désolé, une erreur s'est produite. Veuillez réessayer.\u200B",
      });
    } catch { /* ignore */ }
  }
}

/**
 * Charge un média depuis un chemin local ou une URL distante.
 * (Logique inspirée d'OpenClaw)
 */
async function loadMedia(mediaPathOrUrl: string): Promise<{ buffer: Buffer; mimetype: string; fileName: string }> {
  // 1. Essayer le chemin local direct (plus rapide et stable)
  const localPath = path.join(GENERATED_DIR, mediaPathOrUrl);
  try {
    const stats = await fs.stat(localPath);
    if (stats.isFile()) {
      const buffer = await fs.readFile(localPath);
      const fileName = path.basename(localPath);
      const ext = path.extname(fileName).toLowerCase();
      let mimetype = "application/octet-stream";
      if (ext === ".pdf") mimetype = "application/pdf";
      else if (ext === ".docx") mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
      else if (ext === ".jpg" || ext === ".jpeg") mimetype = "image/jpeg";
      else if (ext === ".png") mimetype = "image/png";
      
      logger.info({ localPath, size: buffer.length }, "Media loaded from disk");
      return { buffer, mimetype, fileName };
    }
  } catch {
    // Si echec, on continue vers le fetch HTTP
  }

  // 2. Fallback HTTP (méthode OpenClaw outbound)
  let url = mediaPathOrUrl;
  if (!url.startsWith("http")) {
    url = `${BASE_URL}/documents/download/${mediaPathOrUrl}`;
  }

  // Hack IP pour environnements Docker/locaux si necessaire
  const hostIp = process.env.HOST_IP;
  if (hostIp) {
    url = url.replace("localhost", hostIp).replace("127.0.0.1", hostIp);
  }

  logger.info({ url }, "Fetching media from URL");
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download media: ${response.status} ${response.statusText}`);
  }

  const mimetype = response.headers.get("content-type") || "application/octet-stream";
  const arrayBuffer = await response.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);
  const fileName = url.split("/").pop()?.split("?")[0] || "file";

  return { buffer, mimetype, fileName };
}

/**
 * Envoie un média avec le type approprié (image, audio, document).
 * (Exactement comme OpenClaw send-api.js)
 */
async function sendMediaMessage(
  jid: string,
  media: { buffer: Buffer; mimetype: string; fileName: string },
  caption?: string
): Promise<void> {
  const { buffer, mimetype, fileName } = media;
  let payload: any;

  if (mimetype.startsWith("image/")) {
    payload = { image: buffer, caption: caption || undefined, mimetype };
  } else if (mimetype.startsWith("audio/")) {
    // WhatsApp attend opus pour les voice notes (PTT)
    const audioMime = mimetype === "audio/ogg" ? "audio/ogg; codecs=opus" : mimetype;
    payload = { audio: buffer, ptt: true, mimetype: audioMime };
  } else if (mimetype.startsWith("video/")) {
    payload = { video: buffer, caption: caption || undefined, mimetype };
  } else {
    // Document (PDF, DOCX, etc.)
    payload = {
      document: buffer,
      mimetype,
      fileName: fileName,
      caption: caption || undefined,
    };
  }

  // Présence "en train d'écrire"
  await sock.sendPresenceUpdate("composing", jid);
  
  // Stabilité : petit délai si connexion trop fraîche
  const timeSinceConnect = Date.now() - connectionOpenTime;
  if (connectionOpenTime > 0 && timeSinceConnect < MIN_STABLE_CONNECTION_MS) {
    await new Promise(r => setTimeout(r, 2000));
  }

  const result = await sock.sendMessage(jid, payload);
  if (!result) throw new Error("Baileys failed to send media");

  logger.info({ jid, type: Object.keys(payload)[0], fileName }, "Media sent successfully");
}

// =============================================================================

async function connectToWhatsApp(): Promise<void> {
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    logger.error("Trop de tentatives. Arrêt.");
    process.exit(1);
  }

  const baileys: any = await import("@whiskeysockets/baileys");
  const makeWASocket = baileys.makeWASocket || baileys.default;
  const useMultiFileAuthState =
    baileys.useMultiFileAuthState || baileys.default?.useMultiFileAuthState;
  const DisconnectReason = baileys.DisconnectReason;

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { fetchLatestBaileysVersion } = baileys;
  const { version, isLatest } = await fetchLatestBaileysVersion();
  logger.info({ version, isLatest }, "Initialisation du bot WhatsApp...");

  sock = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    logger, // On passe explicitement le logger à Baileys
    printQRInTerminal: true,
    syncFullHistory: false,
    // fireInitQueries est nécessaire pour la distribution des clés média (getUSyncDevices).
    // Si désactivé, les médias peuvent être indéchiffrables (erreur phash).
    fireInitQueries: true,
    browser: ["leRH", "Chrome", "110.0.0.0"],
    markOnlineOnConnect: false, // Match OpenClaw
    shouldIgnoreJid: () => false,
    getMessage: async (key: any) => {
      return messageStore.get(key.id);
    },
    defaultQueryTimeoutMs: 120_000, // Augmenté à 2min pour garantir la sync des clés média
  });

  sock.ev.on("creds.update", saveCreds);
  processedMessages.clear();

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
      reconnectAttempts = 0;
      try { sock.sendPresenceUpdate("available"); } catch { /* ignore */ }
      // Attendre STABLE_DELAY_MS avant le premier poll pour laisser la session
      // multi-device se synchroniser (clés Signal, appareils liés, etc.).
      // Sans ce délai, getUSyncDevices échoue et les médias sont indéchiffrables.
      logger.info({ delayMs: STABLE_DELAY_MS }, "En attente de stabilisation de la connexion...");
      setTimeout(() => {
        logger.info("Connexion stable — démarrage du polling");
        pollPendingMessages().catch((err) => logger.error({ err }, "Initial poll failed"));
        setInterval(
          () => pollPendingMessages().catch((err) => logger.error({ err }, "Poll error")),
          10_000
        );
      }, STABLE_DELAY_MS);
    }

    if (connection === "close") {
      const err = lastDisconnect?.error as Boom | undefined;
      const code = err?.output?.statusCode;
      const loggedOut = code === DisconnectReason?.loggedOut;
      const isConflict = err?.data?.type === "replaced";

      if (loggedOut || isConflict) {
        logger.error("Session invalide — supprimez session/ et relancez.");
        if (sock) sock.end(undefined);
        process.exit(1);
      }

      logger.warn({ code }, "❌ Déconnecté");
      reconnectAttempts++;

      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        process.exit(1);
      }

      const delay = Math.min(5000 * reconnectAttempts, 30000);
      logger.info(`Reconnexion dans ${delay / 1000}s...`);
      setTimeout(connectToWhatsApp, delay);
    }
  });

  sock.ev.on("messages.upsert", async (event: any) => {
    try {
      const { messages, type } = event;

      // Stockage systématique pour permettre les retries (erreurs phash)
      for (const m of messages) {
        if (m.key?.id && m.message) {
          messageStore.set(m.key.id, m.message);
        }
        // Mémoriser le JID complet pour cet utilisateur
        if (m.key?.remoteJid) {
          const rawId = m.key.remoteJid.split("@")[0].split(":")[0];
          jidMap.set(rawId, m.key.remoteJid);
        }
      }

      logger.info({ type, count: messages.length }, "messages.upsert");
      if (type !== "notify") return;
      for (const msg of messages) {
        await handleMessage(msg);
      }
    } catch (err) {
      logger.error({ err }, "messages.upsert handler crashed");
    }
  });

  setInterval(() => {
    logger.debug({ wsState: sock?.ws?.readyState, reconnectAttempts }, "Heartbeat");
  }, 30_000);
}

// =============================================================================
// POLLING DES MESSAGES EN ATTENTE
// =============================================================================

interface PendingMessage {
  id: string;
  message_type: string;
  text: string | null;
  document_path: string | null;
  platform_chat_id?: string;
}

async function pollPendingMessages(): Promise<void> {
  if (!sock) return;

  // Attendre si la connexion n'est pas encore stable
  const timeSinceConnect = Date.now() - connectionOpenTime;
  if (connectionOpenTime > 0 && timeSinceConnect < MIN_STABLE_CONNECTION_MS) {
    logger.info({ waitMs: MIN_STABLE_CONNECTION_MS - timeSinceConnect }, "Connection not stable yet, skipping poll");
    return;
  }

  const pendingUrl = `${BASE_URL}/api/whatsapp/pending`;

  try {
    const messages = await apiRequest<PendingMessage[]>("/api/whatsapp/pending");
    if (messages.length === 0) return;

    logger.info({ count: messages.length }, "Processing pending messages");

    for (const msg of messages) {
      const rawId = msg.platform_chat_id || String(msg.id);
      let jid = rawId;

      // Utiliser le JID complet mappé (LID ou PN) si on l'a déjà vu
      if (jidMap.has(rawId)) {
        jid = jidMap.get(rawId)!;
        logger.debug({ rawId, jid }, "Using mapped JID from cache");
      } else if (!jid.includes("@")) {
        // Fallback: si l'ID est très long, c'est probablement un LID
        const suffix = jid.length >= 14 ? "@lid" : "@s.whatsapp.net";
        jid = `${jid}${suffix}`;
        logger.debug({ rawId, jid }, "Guessed JID suffix");
      }

      try {
        if (msg.message_type === "document" && msg.document_path) {
          // Charger le média (priorité local comme OpenClaw)
          const media = await loadMedia(msg.document_path);
          const caption = msg.text || "Ton document est prêt.";

          await sendMediaMessage(jid, media, caption);
          // ACK après envoi réussi — le message ne sera plus retourné par /pending
          await apiRequest("/api/whatsapp/pending/ack", {
            method: "POST",
            body: JSON.stringify({ ids: [msg.id] }),
          }).catch((e) => logger.warn({ e }, "ACK request failed (non-fatal)"));
        } else if (msg.text) {
          await sock.sendMessage(jid, { text: msg.text + "\u200B" });
          logger.info({ id: msg.id }, "Text message sent");
          // ACK après envoi réussi
          await apiRequest("/api/whatsapp/pending/ack", {
            method: "POST",
            body: JSON.stringify({ ids: [msg.id] }),
          }).catch((e) => logger.warn({ e }, "ACK request failed (non-fatal)"));
        }
      } catch (err) {
        logger.error({ err, msgId: msg.id, jid }, "Failed to send pending message");

        // Prévenir l'utilisateur de l'echec
        try {
          const fallbackText =
            "Ton document a été généré, mais l'envoi a échoué.\n\n" +
            "Tape \"mon CV\" ou \"ma lettre\" pour relancer l'envoi.\u200B";
          await sock.sendMessage(jid, { text: fallbackText });
        } catch { /* ignore */ }
      }
    }
  } catch (err) {
    logger.error({ err }, "Error in pollPendingMessages");
  }
}

// =============================================================================

async function checkApiHealth() {
  try {
    const data = await apiRequest("/health");
    logger.info({ data }, "API health OK");
  } catch (err) {
    logger.warn({ err }, "API not reachable on startup");
  }
}

checkApiHealth();

process.on("unhandledRejection", (reason) => {
  logger.error({ err: reason }, "UNHANDLED REJECTION");
});
process.on("uncaughtException", (err) => {
  logger.error({ err }, "UNCAUGHT EXCEPTION");
});
process.on("SIGINT", () => { if (sock) sock.end(undefined); process.exit(0); });
process.on("SIGTERM", () => { if (sock) sock.end(undefined); process.exit(0); });

connectToWhatsApp().catch((err) => {
  logger.fatal({ err }, "Erreur fatale");
  process.exit(1);
});
