# Guide : Telegram + Railway

Ce guide explique comment configurer le bot Telegram pour qu'il communique avec votre backend Alyn déployé sur Railway.

## Architecture

```
Telegram App (Mobile/Desktop)
        ↓
Telegram Bot API
        ↓
Telegram Watcher (Local sur votre Mac)
        ↓ HTTP POST
Railway Backend (https://alyn-backend.up.railway.app)
        ↓
Interaction Agent → Execution Agents
        ↓
Réponse à l'utilisateur via Telegram
```

## Prérequis

1. **Backend déployé sur Railway** : `https://alyn-backend.up.railway.app`
2. **Bot Telegram créé** : Vous devez avoir un token de @BotFather
3. **Node.js 18+** installé localement
4. **Fichier `.env`** configuré

## Configuration

### 1. Créer votre Bot Telegram

1. Ouvrez Telegram et cherchez `@BotFather`
2. Envoyez `/newbot` et suivez les instructions
3. Récupérez votre `TELEGRAM_BOT_TOKEN`
4. Pour obtenir votre `TELEGRAM_CHAT_ID` :
   - Envoyez un message à votre bot
   - Exécutez : `node find_chat_id.js`
   - Ou visitez : `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`

### 2. Configurer les Variables d'Environnement

Créez un fichier `.env` à la racine du projet :

```bash
# Telegram Configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321

# Backend Configuration
BACKEND_MODE=RAILWAY
BACKEND_URL=https://alyn-backend.up.railway.app
BACKEND_ENDPOINT=/api/v1/chat/send

# OpenRouter API Key (doit être configuré sur Railway également)
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

### 3. Installer les Dépendances

```bash
npm install
```

Les dépendances nécessaires :
- `node-telegram-bot-api`: Pour communiquer avec Telegram
- `dotenv`: Pour charger les variables d'environnement

### 4. Lancer le Watcher Telegram

```bash
node server/services/telegram/telegram_watcher.js
```

Vous devriez voir :
```
🚀 Ariel Telegram Watcher initialisé (mode: RAILWAY) - https://alyn-backend.up.railway.app
```

## Utilisation

1. Ouvrez Telegram et trouvez votre bot
2. Envoyez un message : "Bonjour Ariel !"
3. Le watcher reçoit le message et l'envoie au backend Railway
4. Ariel traite le message et répond via Telegram

## Logs et Debugging

Le watcher affiche des logs pour chaque étape :

- `📨 Message Telegram reçu: ...` : Message reçu de l'utilisateur
- `✅ Réponse envoyée sur Telegram (X caractères)` : Réponse envoyée avec succès
- `❌ Erreur HTTP (XXX):` : Erreur lors de la communication avec Railway
- `⏱️  Timeout:` : Le backend a pris plus de 2 minutes

## Configuration Railway (Backend)

Assurez-vous que votre backend Railway a les variables d'environnement suivantes :

```bash
# LLM Configuration
OPENROUTER_API_KEY=your_key_here
ALYN_MODEL=anthropic/claude-sonnet-4

# Composio (pour Gmail, Calendar, etc.)
COMPOSIO_API_KEY=your_key_here
COMPOSIO_GMAIL_AUTH_CONFIG_ID=your_id_here
COMPOSIO_CALENDAR_AUTH_CONFIG_ID=your_id_here

# Server Configuration
OPENPOKE_HOST=0.0.0.0
OPENPOKE_PORT=8000
OPENPOKE_CORS_ALLOW_ORIGINS=*
```

## Interface Web (Settings)

L'interface web reste accessible pour configurer les intégrations :

1. Accédez à votre app Railway web
2. Allez dans **Settings**
3. Connectez votre compte Gmail via Composio OAuth
4. Connectez votre Google Calendar
5. Ces configurations sont stockées sur Railway et utilisables par Telegram

## Modes de Fonctionnement

### Mode RAILWAY (Production)
- Le watcher tourne **localement** sur votre Mac
- Il communique avec le backend **Railway** via HTTP
- Idéal pour l'utilisation quotidienne
- Configure avec : `BACKEND_MODE=RAILWAY`

### Mode LOCAL (Développement)
- Le watcher et le backend tournent **localement**
- Utilise le script Python directement
- Idéal pour le développement et les tests
- Configure avec : `BACKEND_MODE=LOCAL`

## Fonctionnalités Supportées

✅ **Messages Telegram** : Envoyez des questions à Ariel via Telegram
✅ **Agents d'Exécution** : Ariel peut lancer des agents pour rechercher, gérer des emails, etc.
✅ **Gmail Integration** : Via Composio (configuré dans l'interface web)
✅ **Google Calendar** : Via Composio (configuré dans l'interface web)
✅ **Recherche Web** : Via outils de recherche intégrés
✅ **Rappels et Triggers** : Planifier des tâches récurrentes
✅ **Feedback Utilisateur** : Ariel vous informe toujours avant de déléguer à un agent

## Troubleshooting

### Le watcher ne démarre pas
```bash
Error: Cannot find module 'node-telegram-bot-api'
```
**Solution** : `npm install`

### Pas de réponse de Telegram
1. Vérifiez que `TELEGRAM_BOT_TOKEN` est correct
2. Vérifiez que le backend Railway est accessible : `curl https://alyn-backend.up.railway.app/health`
3. Regardez les logs du watcher pour voir les erreurs

### Erreur 502 / 504 (Backend Timeout)
- Le backend Railway peut prendre du temps pour les tâches complexes
- Le timeout est configuré à 2 minutes
- Essayez de simplifier votre requête

### Le bot répond mais ne peut pas envoyer d'emails
- Allez dans l'interface web Settings
- Connectez votre compte Gmail via Composio OAuth
- Les credentials sont stockés sur Railway et accessibles au bot

## Commandes Utiles

```bash
# Lancer le watcher
node server/services/telegram/telegram_watcher.js

# Trouver votre Chat ID
node find_chat_id.js

# Tester le backend Railway
curl -X POST https://alyn-backend.up.railway.app/api/v1/chat/send \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

## Support

Pour toute question ou problème :
1. Vérifiez les logs du watcher Telegram
2. Vérifiez les logs Railway (dans le dashboard Railway)
3. Testez le backend directement avec curl
