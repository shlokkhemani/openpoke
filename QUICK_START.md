# Quick Start - Alyn iMessage Integration

## ⚠️ Important : Vérifiez que vous êtes dans le bon répertoire

```bash
# Vous devez être dans .conductor/tokyo/
pwd
# Résultat attendu : /Users/[votre-nom]/conductor/openpoke/.conductor/tokyo
```

## 🚀 Démarrage en 4 étapes

### 1. Ouvrez l'application Messages
**CRITICAL** : L'application Messages de macOS **doit être ouverte** pour que l'intégration fonctionne.

```bash
# Ouvrez Messages via Spotlight
open -a Messages
```

### 2. Accordez Full Disk Access
1. **Réglages Système** → **Confidentialité et sécurité** → **Accès complet au disque**
2. Ajoutez votre Terminal ou IDE
3. **Redémarrez** votre Terminal/IDE

### 3. Installez les dépendances
```bash
# Assurez-vous d'être dans .conductor/tokyo/
npm install
```

### 4. Testez l'installation
```bash
./test_imessage.sh
```

## 🎯 Lancement

```bash
# Démarrez le watcher iMessage
./start_imessage.sh
```

Vous devriez voir :
```
🚀 Alyn iMessage Watcher initialized
👀 Watching for iMessages (polling every 2000ms)...
📱 Send a message to this Mac via iMessage to test
```

## ✅ Test

Envoyez-vous un iMessage depuis un autre appareil. Vous devriez voir dans le terminal :

```
📨 New message from +1234567890:
   "Hello Alyn!"
✅ Message processed: Message from +1234567890 processed successfully
```

## ❌ Problèmes courants

### Erreur : "Messages app is not running"
→ **Ouvrez l'application Messages** sur votre Mac

### Erreur : "ENOENT: no such file or directory, open package.json"
→ **Vérifiez que vous êtes dans `.conductor/tokyo/`**, pas dans `openpoke/`

### Erreur : "Permission denied"
→ **Accordez Full Disk Access** à votre Terminal/IDE (voir étape 2)

## �� Documentation complète

- **Guide détaillé** : `IMESSAGE_SETUP.md`
- **Documentation technique** : `server/services/imessage/README.md`

## 🆘 Aide rapide

```bash
# Vérifier votre position
pwd

# Installer les dépendances
npm install

# Tester l'installation
./test_imessage.sh

# Démarrer le watcher
./start_imessage.sh

# Tester l'envoi manuel
node server/services/imessage/send_message.js "+33612345678" "Test"
```
