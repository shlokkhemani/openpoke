# Lancer Alyn en Local

## 1. Lancer le serveur Alyn (Python/FastAPI)

Dans un terminal:

```bash
# Activer l'environnement virtuel
source .venv/bin/activate

# Lancer le serveur en mode développement avec auto-reload
python -m server.server --reload

# Ou sans auto-reload
python -m server.server
```

Le serveur sera accessible sur `http://localhost:8000`

### Options disponibles:
- `--host <ip>` : Changer l'hôte (défaut: 0.0.0.0)
- `--port <port>` : Changer le port (défaut: 8000)
- `--reload` : Mode développement avec auto-reload

## 2. Lancer le watcher iMessage (Node.js)

Dans un AUTRE terminal:

```bash
cd /Users/josephmbaibisso/conductor/openpoke/.conductor/tokyo

# Option 1: Lancer avec le script bash (recommandé)
./start_imessage.sh

# Option 2: Lancer directement avec npm
npm run watch
```

Le watcher va:
- Se connecter à la base de données iMessage (`~/Library/Messages/chat.db`)
- Surveiller les nouveaux messages toutes les 2 secondes
- Transmettre les messages à Alyn via le bridge Python
- Afficher les réponses d'Alyn

## 3. Test complet

### Prérequis:
✅ Messages.app doit être ouvert
✅ Full Disk Access activé pour votre Terminal/IDE
✅ Serveur Alyn en cours d'exécution
✅ Watcher iMessage en cours d'exécution

### Flow:
1. Terminal 1: Serveur Alyn tourne sur port 8000
2. Terminal 2: Watcher iMessage surveille les messages
3. iPhone: Tu envoies un message iMessage à ton Mac
4. Watcher: Détecte le message et le transmet à Alyn
5. Alyn: Traite le message et génère une réponse
6. Watcher: Reçoit la réponse et l'envoie via iMessage
7. iPhone: Tu reçois la réponse d'Alyn

## 4. Debugging

### Vérifier que le serveur fonctionne:
```bash
curl http://localhost:8000/health
# Devrait retourner: {"status":"ok"}
```

### Vérifier les logs:
- **Serveur Alyn**: Les logs s'affichent dans le terminal du serveur
- **Watcher iMessage**: Les logs s'affichent dans le terminal du watcher

### Problèmes courants:

**"Messages app is not running"**
→ Ouvre l'app Messages

**"NODE_MODULE_VERSION mismatch"**
→ Le script `start_imessage.sh` rebuild automatiquement better-sqlite3

**"Permission denied accessing chat.db"**
→ Active Full Disk Access pour ton Terminal/IDE dans Paramètres → Confidentialité

**Le watcher détecte mais Alyn ne répond pas**
→ Vérifie que le serveur Alyn tourne sur le port 8000

## 5. Architecture

```
iPhone                    Mac
  ↓                        ↓
iMessage ────────→ Messages.app
                          ↓
                    chat.db (SQLite)
                          ↓
                  Node.js Watcher (imessage_watcher.js)
                          ↓
                  Python Bridge (imessage_bridge.py)
                          ↓
                  Alyn Server (FastAPI:8000)
                          ↓
                  Interaction Agent
                          ↓
                  Réponse générée
                          ↓
                  send_imessage() tool
                          ↓
                  send_message.js
                          ↓
                    Messages.app
                          ↓
                      iMessage
                          ↓
                      iPhone
```
