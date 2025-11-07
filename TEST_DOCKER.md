# 🧪 Tester avec Docker avant de déployer

## Prérequis

- Docker installé: https://www.docker.com/get-started

## Test rapide

```bash
# 1. Build et lancer
docker compose up --build

# 2. Attendre que tout démarre (environ 1-2 minutes)

# 3. Ouvrir dans le navigateur
# Frontend: http://localhost:3000
# Backend: http://localhost:8001
```

## Commandes utiles

```bash
# Voir les logs
docker compose logs -f

# Voir les logs du backend seulement
docker compose logs -f backend

# Voir les logs du frontend seulement
docker compose logs -f frontend

# Arrêter
docker compose down

# Arrêter et supprimer les volumes (ATTENTION: supprime les données!)
docker compose down -v

# Rebuilder après des changements
docker compose up --build
```

## Tester l'API Backend

```bash
# Health check
curl http://localhost:8001/api/v1/health

# Sauvegarder un profil
curl -X POST http://localhost:8001/api/v1/profile/save \
  -H "Content-Type: application/json" \
  -d '{"userName":"Joseph","birthDate":"1990-05-15","location":"Paris"}'

# Charger le profil
curl http://localhost:8001/api/v1/profile/load
```

## Vérifier les volumes

```bash
# Lister les volumes
docker volume ls | grep backend-data

# Inspecter le volume
docker volume inspect tokyo_backend-data
```

## Résolution de problèmes

### Le frontend ne se connecte pas au backend
- Vérifiez que `PY_SERVER_URL=http://backend:8001` dans docker-compose.yml
- Le nom `backend` doit correspondre au nom du service dans docker-compose.yml

### Les données ne persistent pas
- Vérifiez que le volume est bien monté dans docker-compose.yml
- Vérifiez avec `docker volume ls`

### Le build échoue
- Vérifiez que vous êtes dans le bon répertoire
- Essayez `docker compose down` puis `docker compose up --build`

## Si tout fonctionne localement

✅ Vous êtes prêt à déployer sur Railway/Fly.io/VPS!

Suivez les instructions dans `HOSTING_QUICK_START.md`
