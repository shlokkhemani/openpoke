# Configuration Railway : Backend + Telegram Watcher

Ce guide explique comment déployer **Alyn avec le watcher Telegram** sur Railway, tout dans un seul container.

## Architecture

```
Railway Container
    ├── FastAPI Backend (Python) - Port 8001
    └── Telegram Watcher (Node.js) - Communique avec localhost:8001
         ↓
Telegram Bot API
         ↓
Utilisateur Telegram
```

## Variables d'Environnement Railway

Configurez ces variables dans Railway (Settings → Variables) :

### 🔴 OBLIGATOIRES

```bash
# OpenRouter (LLM)
OPENROUTER_API_KEY=sk-or-v1-xxxxx

# Telegram Bot
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321

# Composio (pour Gmail et Calendar)
COMPOSIO_API_KEY=xxxxx
COMPOSIO_GMAIL_AUTH_CONFIG_ID=xxxxx
COMPOSIO_CALENDAR_AUTH_CONFIG_ID=xxxxx
```

### ⚙️ OPTIONNELLES (avec valeurs par défaut)

```bash
# Configuration LLM
ALYN_MODEL=anthropic/claude-sonnet-4

# Configuration Serveur
OPENPOKE_HOST=0.0.0.0
OPENPOKE_PORT=8001
OPENPOKE_CORS_ALLOW_ORIGINS=*

# Watcher Mode (automatique sur Railway)
# BACKEND_MODE sera automatiquement mis à LOCAL par start-railway.sh
```

## Comment Obtenir TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID

### 1. Créer votre Bot Telegram

1. Ouvrez Telegram et cherchez `@BotFather`
2. Envoyez `/newbot`
3. Suivez les instructions (nom du bot, username)
4. **Copiez le token** fourni par BotFather
5. Ajoutez-le dans Railway : `TELEGRAM_BOT_TOKEN=votre_token_ici`

### 2. Obtenir votre Chat ID

**Option A : Via le script find_chat_id.js (en local)**
```bash
# 1. Envoyez un message à votre bot sur Telegram
# 2. Exécutez localement :
node find_chat_id.js
```

**Option B : Via l'API Telegram**
```bash
# 1. Envoyez un message à votre bot sur Telegram
# 2. Visitez cette URL dans votre navigateur (remplacez YOUR_BOT_TOKEN) :
https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates

# 3. Cherchez "chat":{"id":123456789
# 4. Copiez le nombre après "id":
```

**Option C : Via Railway Logs (après déploiement)**
```bash
# 1. Déployez sur Railway SANS TELEGRAM_CHAT_ID
# 2. Le watcher affichera un warning
# 3. Envoyez un message à votre bot
# 4. Regardez les logs Railway, ils afficheront votre chat_id
# 5. Ajoutez-le dans les variables Railway et redéployez
```

## Déploiement sur Railway

### 1. Configuration Initiale

Dans Railway :
1. Créez un nouveau projet
2. Connectez votre repo GitHub `m0ahs/openpoke`
3. Railway détectera automatiquement le Dockerfile

### 2. Configuration du Build

Dans Railway Settings → Deploy :
- **Build Command** : (laisser vide, Docker s'occupe de tout)
- **Dockerfile Path** : `Dockerfile.backend`
- **Watch Paths** : `/server`, `/start-railway.sh`, `/package.json`

### 3. Ajoutez les Variables d'Environnement

Dans Settings → Variables, ajoutez toutes les variables listées ci-dessus.

**IMPORTANT :** N'oubliez pas :
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `OPENROUTER_API_KEY`

### 4. Déployez

Railway va :
1. Builder l'image Docker (avec Python + Node.js)
2. Installer les dépendances Python et Node.js
3. Lancer `start-railway.sh` qui démarre :
   - Le backend FastAPI (port 8001)
   - Le watcher Telegram (en mode LOCAL, communique avec localhost:8001)

### 5. Vérifiez les Logs

Dans Railway, allez dans l'onglet **Deployments** puis cliquez sur votre déploiement.

Vous devriez voir :
```
==========================================
Starting Alyn on Railway
==========================================
✅ TELEGRAM_BOT_TOKEN found
✅ OPENROUTER_API_KEY found

Starting FastAPI backend...
✅ Backend started (PID: 123)
Waiting for backend to be ready...
✅ Backend is ready!

Starting Telegram watcher...
✅ Telegram watcher started (PID: 456)

==========================================
Alyn is running on Railway
Backend PID: 123
Watcher PID: 456
==========================================
```

## Test

1. Ouvrez Telegram
2. Trouvez votre bot (le nom que vous avez créé avec @BotFather)
3. Envoyez un message : "Bonjour Ariel !"
4. Vous devriez recevoir une réponse !

## Architecture du Déploiement

```
Railway Container
    │
    ├─ start-railway.sh (script de démarrage)
    │   │
    │   ├─ Lance FastAPI (python -m server.server)
    │   │   └─ Port 8001
    │   │
    │   └─ Lance Telegram Watcher (node server/services/telegram/telegram_watcher.js)
    │       └─ BACKEND_MODE=LOCAL (localhost:8001)
    │
    └─ Les deux processus tournent en parallèle
```

## Fonctionnalités Disponibles

Une fois déployé, votre bot Telegram peut :

✅ Répondre à vos messages
✅ Lancer des agents pour rechercher des informations
✅ Gérer vos emails via Gmail (après OAuth via l'interface web)
✅ Gérer votre calendrier via Google Calendar
✅ Créer des rappels et tâches planifiées
✅ Effectuer des recherches web

## Interface Web (pour OAuth Gmail/Calendar)

Railway expose automatiquement votre backend sur une URL publique comme :
```
https://openpoke-production.up.railway.app
```

Utilisez cette URL pour :
1. Accéder à l'interface web (`/`)
2. Configurer Gmail OAuth (Settings → Gmail → Connect)
3. Configurer Calendar OAuth (Settings → Calendar → Connect)

Ces configurations sont ensuite utilisables par votre bot Telegram !

## Troubleshooting

### Le watcher ne démarre pas

**Problème :** Logs Railway montrent "TELEGRAM_BOT_TOKEN not set"

**Solution :** Vérifiez que vous avez bien ajouté `TELEGRAM_BOT_TOKEN` dans Railway Variables.

### Le bot ne répond pas

**Problème :** Le bot reçoit les messages mais ne répond pas

**Solutions :**
1. Vérifiez les logs Railway pour voir les erreurs
2. Vérifiez que `OPENROUTER_API_KEY` est correctement configuré
3. Vérifiez que le backend est bien démarré (vous devriez voir "Backend is ready!")

### Erreur "Backend failed to start within 30 seconds"

**Problème :** Le backend prend trop de temps à démarrer

**Solution :**
- Vérifiez que toutes les dépendances sont installées
- Regardez les logs Python pour voir l'erreur exacte
- Vérifiez que `OPENROUTER_API_KEY` est valide

### Le watcher se connecte mais rate les messages

**Problème :** `TELEGRAM_CHAT_ID` incorrect

**Solution :**
1. Vérifiez votre `TELEGRAM_CHAT_ID` avec l'API Telegram
2. Assurez-vous que c'est un nombre (pas de quotes)
3. Redéployez après avoir corrigé

## Redéploiement

Après avoir modifié le code :

```bash
git add -A
git commit -m "feat: update xyz"
git push origin launch-project
```

Railway détectera automatiquement le push et redéploiera.

## Coûts Railway

- **Free Plan** : 500 heures/mois (suffisant pour tester)
- **Hobby Plan** : $5/mois (recommandé pour production)

Avec le watcher Telegram + backend dans un seul container, vous n'utilisez qu'**un seul service Railway**.

## Support

Si vous rencontrez des problèmes :
1. Consultez les logs Railway (Deployments → View Logs)
2. Vérifiez que toutes les variables d'environnement sont correctement configurées
3. Testez le backend directement : `curl https://votre-url.railway.app/health`
