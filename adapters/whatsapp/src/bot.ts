/**
 * leRH — WhatsApp Bot (Baileys)
 */

import { Boom } from "@hapi/boom";
import { downloadContentFromMessage, jidNormalizedUser } from "@whiskeysockets/baileys";
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

// =============================================================================
// ENVOI DE DOCUMENTS — explication de la syntaxe Baileys correcte
// =============================================================================
//
// ERREURS COMMUNES avec Baileys pour les documents :
//
// ❌ MAUVAIS — caption dans le contenu (ignoré ou rejeté pour les documents) :
//    sock.sendMessage(jid, { document: buf, fileName: "f.docx", caption: "..." })
//
// ❌ MAUVAIS — buffer brut sans vérification de taille :
//    const buf = Buffer.from(await res.arrayBuffer())
//    sock.sendMessage(jid, { document: buf, ... })
//    → échoue silencieusement si buf est vide ou corrompu
//
// ✅ BON — URL directe, Baileys streame vers WA sans charger en mémoire :
//    sock.sendMessage(jid, { document: { url: "http://..." }, fileName: "f.docx", mimetype: "..." })
//
// ✅ BON — caption en message texte séparé (toujours visible) :
//    await sock.sendMessage(jid, { document: { url }, fileName, mimetype })
//    await sock.sendMessage(jid, { text: "Votre CV est prêt !" })
//
// NOTE : l'URL passée à Baileys doit être accessible depuis le réseau
//        du processus Node.js (pas depuis le navigateur de l'utilisateur).
//        En Docker : utiliser le nom du service interne (ex: http://api:8000).
// =============================================================================

function getMimetype(filename: string): string {
  if (filename.endsWith(".docx")) {
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  }
  if (filename.endsWith(".pdf")) {
    return "application/pdf";
  }
  return "application/octet-stream";
}

/**
 * Envoie un document via Baileys.
 *
 * Stratégie :
 * 1. Passer l'URL directement à Baileys (recommandé, plus fiable).
 *    Baileys streame le fichier depuis l'URL vers les serveurs WhatsApp.
 * 2. Si ça échoue, télécharger le buffer et réessayer.
 * 3. Envoyer la légende dans un message texte séparé (plus compatible).
 */
async function sendDocumentMessage(
  jid: string,
  documentUrl: string,
  filename: string,
  caption: string
): Promise<void> {
  const cleanFilename = filename.replace(/[^a-zA-Z0-9_\.]/g, "_");
  const mimetype = getMimetype(cleanFilename);

  // Vérifier que la connexion est stable avant d'envoyer un média.
  // Un envoi sur connexion instable → phash ack → PDF indéchiffrable côté téléphone.
  const wsState = sock?.ws?.readyState;
  const elapsed = Date.now() - connectionOpenTime;
  if (wsState !== 1 /* WebSocket.OPEN */) {
    throw new Error(`WebSocket not open (state=${wsState}) — skip media send`);
  }
  if (elapsed < STABLE_DELAY_MS) {
    throw new Error(
      `Connexion trop récente (${elapsed}ms < ${STABLE_DELAY_MS}ms) — skip media send`
    );
  }

  // Convertir localhost en IP accessible
  const accessibleUrl = documentUrl
    .replace("localhost", process.env.HOST_IP || "192.168.1.70")
    .replace("127.0.0.1", process.env.HOST_IP || "192.168.1.70");

  const finalCaption = caption
    ? `${caption}\n\nLien de secours : ${accessibleUrl}`
    : `Lien de secours : ${accessibleUrl}`;

  logger.info({ jid, documentUrl: accessibleUrl, filename: cleanFilename, mimetype }, "Sending document via URL method");

  try {
    const sentMsg = await sock.sendMessage(jid, {
      document: { url: accessibleUrl },
      mimetype,
      fileName: cleanFilename,
      caption: finalCaption,
    });
    if (sentMsg?.key?.id && sentMsg.message) {
      messageStore.set(sentMsg.key.id, sentMsg.message);
    }

    logger.info({ filename: cleanFilename }, "Document sent successfully via URL stream");

    // Fallback ABSOLU : Si WA drop le document + caption, ce message texte passera toujours
    await new Promise((r) => setTimeout(r, 600));
    const fallbackMsg = await sock.sendMessage(jid, {
      text: `📎 Document prêt ! Si le fichier ne s'affiche pas, utilise ce lien :\n${accessibleUrl}\n\u200B`,
    });
    if (fallbackMsg?.key?.id && fallbackMsg.message) {
      messageStore.set(fallbackMsg.key.id, fallbackMsg.message);
    }

  } catch (err: any) {
    logger.error({ err: err?.message, documentUrl: accessibleUrl }, "Failed to send document");
    throw err;
  }
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
    auth: state,
    printQRInTerminal: true,
    syncFullHistory: false,
    // Désactivé : fireInitQueries cause des timeouts qui empêchent la distribution
    // des clés média (getUSyncDevices), rendant les PDF indéchiffrables côté téléphone.
    fireInitQueries: false,
    browser: ["leRH", "Chrome", "0.1.0"],
    markOnlineOnConnect: true,
    shouldIgnoreJid: () => false,
    getMessage: async (key: any) => messageStore.get(key.id),
    defaultQueryTimeoutMs: 30_000,
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

  const pendingUrl = `${BASE_URL}/api/whatsapp/pending`;

  try {
    const res = await fetch(pendingUrl);
    if (!res.ok) {
      logger.warn({ status: res.status }, "Failed to fetch pending messages");
      return;
    }

    const messages: PendingMessage[] = await res.json();
    if (messages.length === 0) return;

    logger.info({ count: messages.length }, "Processing pending messages");

    for (const msg of messages) {
      let jid = msg.platform_chat_id || String(msg.id);
      if (!jid.includes("@")) {
        jid = `${jid}@s.whatsapp.net`;
      }

      try {
        if (msg.message_type === "document" && msg.document_path) {
          // document_path = "user_id/filename.docx"
          // Endpoint FastAPI : GET /documents/download/{filepath:path}
          const documentUrl = encodeURI(`${BASE_URL}/documents/download/${msg.document_path}`);
          const filename = msg.document_path.split("/").pop() || "document.docx";
          const caption = msg.text || "Votre document est prêt ! 📎";

          await sendDocumentMessage(jid, documentUrl, filename, caption);
        } else if (msg.text) {
          await sock.sendMessage(jid, { text: msg.text + "\u200B" });
          logger.info({ id: msg.id }, "Text message sent");
        }
      } catch (err) {
        logger.error({ err, msgId: msg.id, jid }, "Failed to send pending message");

        // Prévenir l'utilisateur de l'echec
        try {
          const fallbackText =
            "📎 Votre document a été généré mais l'envoi a échoué.\n" +
            "Tapez 'mon cv' ou 'ma lettre' pour relancer l'envoi.\u200B";
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
    const res = await fetch(`${BASE_URL}/health`);
    const data = await res.json();
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