# Guide de Déploiement Alyn

## Option 1: Railway.app (Recommandé - Le plus simple)

### Prérequis
- Un compte GitHub
- Un compte Railway.app (gratuit)

### Étapes

1. **Pousser le code sur GitHub**
   ```bash
   git add .
   git commit -m "Prepare for deployment"
   git push origin main
   ```

2. **Créer un nouveau projet sur Railway**
   - Allez sur https://railway.app
   - Cliquez sur "New Project"
   - Sélectionnez "Deploy from GitHub repo"
   - Choisissez votre repo

3. **Déployer le Backend**
   - Railway va détecter automatiquement le projet
   - Ajoutez un nouveau service: "Backend"
   - Dans les settings:
     - **Build Command**: Laisser vide (utilise Dockerfile.backend)
     - **Dockerfile Path**: `Dockerfile.backend`
     - **Port**: `8001`

   - Ajoutez les variables d'environnement:
     ```
     OPENROUTER_API_KEY=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
     COMPOSIO_API_KEY=ak_lccaZmGAOY3FaXiCRJLg
     COMPOSIO_GMAIL_AUTH_CONFIG_ID=ac_-3cIgi-AWyJw
     ```

   - Ajoutez un **Volume** pour persister les données:
     - Mount Path: `/app/server/data`
     - Size: 1GB (suffisant)

4. **Déployer le Frontend**
   - Ajoutez un nouveau service: "Frontend"
   - Dans les settings:
     - **Dockerfile Path**: `Dockerfile.frontend`
     - **Port**: `3000`

   - Ajoutez la variable d'environnement:
     ```
     PY_SERVER_URL=https://votre-backend.railway.app
     ```
     (Remplacez par l'URL de votre backend Railway)

5. **Générer un domaine public**
   - Dans les settings du Frontend
   - Section "Networking"
   - Cliquez sur "Generate Domain"
   - Vous obtiendrez une URL comme: `alyn-frontend.railway.app`

6. **C'est prêt!** 🎉
   - Visitez votre URL Railway
   - Alyn est maintenant accessible 24/7

---

## Option 2: Fly.io (Alternative économique)

### Installation
```bash
# Installer Fly CLI
curl -L https://fly.io/install.sh | sh
```

### Déploiement Backend
```bash
# Se connecter
fly auth login

# Créer l'app backend
fly launch --name alyn-backend --dockerfile Dockerfile.backend --region cdg

# Configurer les secrets
fly secrets set OPENROUTER_API_KEY=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
fly secrets set COMPOSIO_API_KEY=ak_lccaZmGAOY3FaXiCRJLg
fly secrets set COMPOSIO_GMAIL_AUTH_CONFIG_ID=ac_-3cIgi-AWyJw

# Créer un volume pour les données
fly volumes create alyn_data --size 1 --region cdg

# Modifier fly.toml pour monter le volume:
# [mounts]
#   source = "alyn_data"
#   destination = "/app/server/data"

# Déployer
fly deploy
```

### Déploiement Frontend
```bash
# Créer l'app frontend
fly launch --name alyn-frontend --dockerfile Dockerfile.frontend --region cdg

# Configurer l'URL du backend
fly secrets set PY_SERVER_URL=https://alyn-backend.fly.dev

# Déployer
fly deploy
```

Votre app sera sur: `https://alyn-frontend.fly.dev`

---

## Option 3: VPS (DigitalOcean, Hetzner, etc.)

### Prérequis
- Un VPS Ubuntu 22.04
- Docker et Docker Compose installés

### Étapes

1. **Se connecter au VPS**
   ```bash
   ssh root@votre-ip
   ```

2. **Installer Docker**
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   apt install docker-compose-plugin
   ```

3. **Cloner le projet**
   ```bash
   git clone votre-repo
   cd projet
   ```

4. **Créer le fichier .env**
   ```bash
   cat > .env << EOF
   OPENROUTER_API_KEY=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
   COMPOSIO_API_KEY=ak_lccaZmGAOY3FaXiCRJLg
   COMPOSIO_GMAIL_AUTH_CONFIG_ID=ac_-3cIgi-AWyJw
   EOF
   ```

5. **Lancer avec Docker Compose**
   ```bash
   docker compose up -d
   ```

6. **Configurer Nginx (optionnel)**
   ```bash
   apt install nginx certbot python3-certbot-nginx

   # Créer la config Nginx
   nano /etc/nginx/sites-available/alyn
   ```

   Contenu:
   ```nginx
   server {
       listen 80;
       server_name votre-domaine.com;

       location / {
           proxy_pass http://localhost:3000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_cache_bypass $http_upgrade;
       }
   }
   ```

   ```bash
   ln -s /etc/nginx/sites-available/alyn /etc/nginx/sites-enabled/
   nginx -t
   systemctl reload nginx

   # Obtenir SSL gratuit
   certbot --nginx -d votre-domaine.com
   ```

---

## Tester le déploiement

1. Visitez votre URL
2. Allez dans Settings
3. Remplissez votre profil
4. Testez la conversation
5. Si Gmail est configuré, testez la connexion Gmail

---

## Coûts estimés

| Service | Prix | Notes |
|---------|------|-------|
| Railway.app | $5-10/mois | Le plus simple, bon pour débuter |
| Fly.io | $3-5/mois | Économique, bon rapport qualité/prix |
| DigitalOcean | $6/mois | Droplet de base, contrôle total |
| Hetzner | €4.5/mois | Le moins cher, excellent rapport |

---

## Backup des données

Les données importantes sont dans `/app/server/data/`:
- `alyn_conversation.log` - Historique des conversations
- `user_profile.json` - Votre profil
- `triggers.db` - Vos rappels
- `gmail_seen.json` - État Gmail

**Sur Railway/Fly:** Les volumes sont automatiquement backupés
**Sur VPS:** Utilisez un cron job pour backup régulier

```bash
# Backup automatique quotidien
crontab -e

# Ajouter:
0 2 * * * tar -czf /root/backup-$(date +\%Y\%m\%d).tar.gz /path/to/server/data
```

---

## Support

Pour des questions ou problèmes:
1. Vérifiez les logs: `docker compose logs -f`
2. Vérifiez les variables d'environnement
3. Vérifiez que les volumes sont bien montés
