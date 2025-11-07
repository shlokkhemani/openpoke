// Telegram Watcher for Ariel
// Supports both LOCAL (Python script) and RAILWAY (HTTP API) backends

import TelegramBot from 'node-telegram-bot-api';
import { spawn } from 'child_process';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

dotenv.config();
// Gestion de __dirname compatible ES module
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const PYTHON_BRIDGE_PATH = join(__dirname, '../../../telegram_bridge.py');
const VENV_PYTHON = join(__dirname, '../../../.venv/bin/python');
const CHAT_ID = process.env.TELEGRAM_CHAT_ID;

// Configuration backend : LOCAL (default) ou RAILWAY
// On Railway, even if BACKEND_MODE=LOCAL, we use HTTP to localhost instead of spawn
// Use 127.0.0.1 instead of localhost to force IPv4 (avoids IPv6 connection issues)
const IS_RAILWAY = process.env.RAILWAY_ENVIRONMENT !== undefined;
const BACKEND_MODE = IS_RAILWAY ? 'RAILWAY' : (process.env.BACKEND_MODE || 'LOCAL');
const BACKEND_URL = IS_RAILWAY ? 'http://127.0.0.1:8001' : (process.env.BACKEND_URL || 'https://alyn-backend.up.railway.app');
const BACKEND_ENDPOINT = process.env.BACKEND_ENDPOINT || '/api/v1/telegram/message';

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });

console.log(`🚀 Ariel Telegram Watcher initialisé (mode: ${BACKEND_MODE})${BACKEND_MODE === 'RAILWAY' ? ` - ${BACKEND_URL}` : ''}`);

bot.on('message', async (msg) => {
  const chatId = msg.chat.id;
  const text = msg.text;

  // Ignore non-text messages
  if (!text) {
    return;
  }

  console.log(`📨 Message Telegram reçu: ${text}`);

  // Choix du backend selon le mode configuré
  if (BACKEND_MODE === 'RAILWAY') {
    await handleRailwayBackend(chatId, text);
  } else {
    await handleLocalBackend(chatId, text);
  }
});

// Mode LOCAL : Lance le script Python localement
async function handleLocalBackend(chatId, text) {
  const pythonProcess = spawn(VENV_PYTHON, [
    PYTHON_BRIDGE_PATH,
    '--sender', chatId,
    '--text', text,
    '--timestamp', new Date().toISOString()
  ], {
    env: { ...process.env }
  });

  let stdout = '';
  let stderr = '';
  let processEnded = false;

  // Timeout de 2 minutes (120 secondes) pour éviter que le processus bloque indéfiniment
  const TIMEOUT_MS = 120000;
  const timeoutId = setTimeout(() => {
    if (!processEnded) {
      processEnded = true;
      pythonProcess.kill('SIGTERM'); // Tente un arrêt propre

      setTimeout(() => {
        if (!pythonProcess.killed) {
          pythonProcess.kill('SIGKILL'); // Force l'arrêt si nécessaire
        }
      }, 5000);

      console.error('⏱️  Timeout: le processus Python a pris plus de 2 minutes');
      bot.sendMessage(chatId, 'Désolé, le traitement a pris trop de temps. Réessaie avec un message plus court ou reformulé.', {
        disable_notification: false
      });
    }
  }, TIMEOUT_MS);

  pythonProcess.stdout.on('data', (data) => {
    stdout += data.toString();
  });

  pythonProcess.stderr.on('data', (data) => {
    // Les logs Python vont vers stderr, on les accumule pour vérification
    stderr += data.toString();
  });

  pythonProcess.on('close', (code) => {
    if (processEnded) return; // Déjà géré par le timeout

    processEnded = true;
    clearTimeout(timeoutId);
    
    const response = stdout.trim();
    // Ne considère comme erreur que les vraies erreurs (traceback, exceptions)
    // Les logs INFO/WARNING dans stderr ne sont pas des erreurs
    const hasTraceback = stderr.includes('Traceback') || 
                        stderr.includes('File "') || 
                        stderr.includes('Exception:') ||
                        (stderr.includes('Error:') && stderr.includes('at '));
    const isRealError = code !== 0 && hasTraceback;
    
    if (isRealError) {
      // Vraie erreur : on l'affiche et on informe l'utilisateur
      console.error(`❌ Erreur Python (code ${code}):`, stderr.substring(0, 500) || '(aucun détail)');
      bot.sendMessage(chatId, 'Désolé, une erreur s\'est produite lors du traitement de ton message.', {
        disable_notification: false // Force la notification même en cas d'erreur
      });
    } else if (response !== '' && !response.startsWith('Erreur:')) {
      // Succès : on envoie la réponse avec notification
      bot.sendMessage(chatId, response, {
        disable_notification: false // Force la notification
      });
      console.log(`✅ Réponse envoyée sur Telegram (${response.length} caractères)`);
    } else if (response.startsWith('Erreur:')) {
      // Erreur dans la réponse (mais pas de traceback)
      const errorMsg = response.replace('Erreur: ', '');
      bot.sendMessage(chatId, `⚠️ ${errorMsg}`, {
        disable_notification: false
      });
      console.log(`⚠️ Erreur dans la réponse: ${errorMsg}`);
    } else {
      // Aucune réponse mais pas d'erreur (cas : duplicata détecté, tool wait utilisé, etc.)
      const responsePreview = response ? response.substring(0, 50) : '(vide)';
      console.log(`⚠️  Aucune réponse générée (code: ${code}, stdout: "${responsePreview}", stderr length: ${stderr.length})`);
      // Informe l'utilisateur qu'il n'y a pas eu de réponse
      bot.sendMessage(chatId, 'Je n\'ai pas généré de réponse pour ce message. Peut-être que c\'était un doublon ou que j\'ai utilisé un outil silencieux. Réessaie si besoin.', {
        disable_notification: false
      });
    }
  });

  pythonProcess.on('error', (err) => {
    if (processEnded) return;
    processEnded = true;
    clearTimeout(timeoutId);
    stopTyping();
    console.error('❌ Erreur lors du lancement du processus Python:', err);
    bot.sendMessage(chatId, 'Désolé, impossible de lancer le traitement de ton message.', {
      disable_notification: false
    });
  });
}

// Mode RAILWAY : Appelle l'API HTTP du backend Railway (async processing)
// The backend will push responses directly to Telegram as they become available
async function handleRailwayBackend(chatId, text) {
  const url = `${BACKEND_URL}${BACKEND_ENDPOINT}`;
  const timeout = 30000; // 30 seconds - allows for Railway redeploys and cold starts

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        message: text,
        chat_id: chatId.toString()
      }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (response.ok || response.status === 202) {
      // Message accepted for processing
      console.log(`✅ Message envoyé au backend (status: ${response.status})`);
      // Note: Responses will be pushed directly from the Python backend via Telegram API
      // No need to wait or send anything here
    } else {
      console.error(`❌ Erreur HTTP (${response.status}) lors de l'envoi du message`);
      // Send error to user
      bot.sendMessage(chatId, 'Désolé, impossible d\'envoyer ton message au backend.', {
        disable_notification: false
      });
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      console.error('⏱️  Timeout: le backend n\'a pas accepté le message');
      bot.sendMessage(chatId, 'Désolé, le serveur ne répond pas. Réessaie dans quelques instants.', {
        disable_notification: false
      });
    } else {
      console.error('❌ Erreur lors de la requête Railway:', err);
      bot.sendMessage(chatId, 'Désolé, impossible de contacter le serveur. Réessaie dans quelques instants.', {
        disable_notification: false
      });
    }
  }
}

// Arrêt propre
process.on('SIGINT', () => {
  console.log('\n\n👋 Arrêt du Telegram Watcher...');
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('\n\n👋 Arrêt du Telegram Watcher...');
  process.exit(0);
});
