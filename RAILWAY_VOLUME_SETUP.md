# Railway Volume Data Management System

## Overview

Ce système utilise les **Railway Volumes** pour persister toutes les données de Ariel de manière robuste et sécurisée.

## Configuration Railway

**Volume actuel :**
- **Mount Path** : `/app/server/data`
- **Taille** : 500 MB
- **Région** : EU West (Amsterdam, Netherlands)
- **Persistence** : Garantie entre redéploiements

## Architecture

### Structure des données

```
/app/server/data/                    # Railway Volume mount point
├── user_profile.json                # Profil utilisateur
├── lessons_learned.json             # Leçons apprises par Ariel
├── metadata.json                    # Métadonnées système
├── backups/                         # Sauvegardes automatiques
│   ├── user_profile_20250106_143022.json
│   ├── user_profile_20250106_152314.json
│   └── lessons_learned_20250106_143022.json
└── conversation_history/            # Historique (futur)
```

### DataManager Centralisé

**Fichier** : `server/services/data_manager.py`

**Fonctionnalités** :
- ✅ **Écritures atomiques** - Pas de corruption si crash pendant l'écriture
- ✅ **Backups automatiques** - Avant chaque modification importante
- ✅ **Rotation des backups** - Garde les 5 derniers backups par fichier
- ✅ **Thread-safe** - Gestion concurrente sécurisée
- ✅ **Validation des données** - Détection et récupération auto des fichiers corrompus
- ✅ **Health checks** - Monitoring de l'espace disque et des backups

## Utilisation

### Sauvegarder des données

```python
from server.services.data_manager import get_data_manager

data_manager = get_data_manager()

# Sauvegarder avec backup automatique
data = {"userName": "Alex", "location": "Paris"}
data_manager.save_json("user_profile.json", data, backup=True)
```

### Charger des données

```python
# Charger (retourne {} si fichier n'existe pas)
profile = data_manager.load_json("user_profile.json")
```

### Mettre à jour un champ

```python
# Update atomique avec backup
data_manager.update_field("user_profile.json", "location", "Lyon", backup=True)
```

### Restaurer depuis backup

```python
# Restaure automatiquement depuis le backup le plus récent
success = data_manager.restore_from_backup("user_profile.json")
```

## Services intégrés

### UserProfile

**Fichier** : `server/services/user_profile.py`

```python
from server.services.user_profile import get_user_profile

profile_service = get_user_profile()

# Sauvegarder
profile_service.save({"userName": "Alex", "birthDate": "1990-01-01"})

# Charger
data = profile_service.load()

# Restaurer depuis backup
profile_service.restore_from_backup()
```

### LessonsLearned

**Fichier** : `server/services/lessons_learned.py`

```python
from server.services.lessons_learned import get_lessons_service

lessons = get_lessons_service()

# Ajouter une leçon
lessons.add_lesson(
    category="messaging",
    problem="Messages trop longs",
    solution="Limiter à 500 caractères max"
)

# Récupérer les leçons
all_lessons = lessons.get_lessons()
```

## API Admin Endpoints

### Health Check

```bash
GET /api/v1/data-admin/health
```

**Réponse** :
```json
{
  "status": "healthy",
  "mount_path": "/app/server/data",
  "total_size_mb": 0.15,
  "backup_size_mb": 0.08,
  "backup_count": 3,
  "metadata": { "schema_version": "1.0.0", ... }
}
```

### Storage Info

```bash
GET /api/v1/data-admin/storage-info
```

**Réponse** :
```json
{
  "mount_path": "/app/server/data",
  "data_files": [
    {"name": "user_profile.json", "size_kb": 1.2},
    {"name": "lessons_learned.json", "size_kb": 3.5}
  ],
  "backups": [...],
  "summary": {
    "total_size_mb": 0.2,
    "usage_percent": 0.04,
    "volume_limit_mb": 500
  }
}
```

### Export toutes les données

```bash
GET /api/v1/data-admin/export
```

**Réponse** :
```json
{
  "success": true,
  "data": {
    "exported_at": "2025-01-06T14:30:22",
    "files": {
      "user_profile.json": { "userName": "..." },
      "lessons_learned.json": { "lessons": [...] }
    }
  }
}
```

### Restaurer depuis backup

```bash
POST /api/v1/data-admin/restore-backup
Content-Type: application/json

{
  "filename": "user_profile.json"
}
```

## Avantages vs Base de données

### Pourquoi JSON + Volume (pour usage solo) ?

✅ **Simplicité**
- Pas de setup PostgreSQL
- Pas de migrations SQL
- Pas de ORM à configurer

✅ **Coût**
- 0€ supplémentaire
- Inclus dans Railway volume (gratuit jusqu'à 500MB)

✅ **Performance**
- Lecture instantanée (tout en mémoire si nécessaire)
- Pas de latence réseau

✅ **Debugging**
- Fichiers JSON lisibles directement
- Export/import facile

✅ **Backups**
- Automatiques et versionnés
- Restauration en 1 clic

### Quand migrer vers PostgreSQL ?

❌ **Si tu passes en multi-utilisateurs**
- Besoin de profils par `chat_id`
- Gestion de permissions

❌ **Si tu veux des queries complexes**
- Recherche full-text
- Agrégations
- Jointures

❌ **Si tu stockes beaucoup de données**
- > 100MB de données JSON
- Historique de milliers de conversations

## Sécurité

### Atomic Writes

Le DataManager utilise une technique d'écriture atomique :

1. Écrire dans un fichier temporaire `.tmp`
2. Flush vers le disque
3. Renommer atomiquement (opération POSIX garantie)

→ **Jamais de corruption**, même si crash pendant l'écriture

### Backups automatiques

Avant chaque modification importante :
1. Copie du fichier actuel → `backups/filename_TIMESTAMP.json`
2. Rotation (garde les 5 derniers)
3. Modification du fichier principal

### Récupération auto

Si un fichier JSON est corrompu :
1. Détection automatique lors de la lecture
2. Log de l'erreur
3. Restauration depuis le backup le plus récent
4. Retry de la lecture

## Monitoring

### Sur Railway Dashboard

- **Volume Usage** : Espace utilisé / 500 MB
- **Backups** : Liste des backups via Railway UI
- **Alerts** : Configure des alertes si > 80% utilisé

### Via API

```bash
# Health check rapide
curl https://alyn.up.railway.app/api/v1/data-admin/health

# Storage détaillé
curl https://alyn.up.railway.app/api/v1/data-admin/storage-info
```

## Maintenance

### Nettoyer les vieux backups

Les backups sont automatiquement rotés (5 max par fichier).

Si besoin manuel :
```bash
# SSH dans Railway container
railway shell

# Lister les backups
ls -lh /app/server/data/backups/

# Supprimer manuellement (si nécessaire)
rm /app/server/data/backups/old_backup_*.json
```

### Export manuel

Pour backup externe (Google Drive, etc.) :

```bash
# Export via API
curl https://alyn.up.railway.app/api/v1/data-admin/export > seline_backup.json

# Ou depuis le code
python -c "
from server.services.data_manager import get_data_manager
import json
export = get_data_manager().export_all_data()
print(json.dumps(export, indent=2))
" > backup.json
```

## Migration future vers PostgreSQL

Si tu décides de migrer :

```python
# Script de migration (exemple)
from server.services.data_manager import get_data_manager
from your_db import UserModel, session

# Export
data_manager = get_data_manager()
export = data_manager.export_all_data()

# Import vers DB
for file, content in export["files"].items():
    if file == "user_profile.json":
        user = UserModel(**content)
        session.add(user)
        session.commit()
```

## FAQ

**Q: Les données survivent aux redéploiements ?**
A: ✅ Oui, tant que le volume Railway est monté sur `/app/server/data`

**Q: Que se passe-t-il si Railway redémarre ?**
A: ✅ Les données persistent, seul le container est recréé

**Q: Puis-je accéder aux backups ?**
A: ✅ Oui, via Railway Dashboard > Volumes ou via API `/data-admin/storage-info`

**Q: Limite de taille ?**
A: 500 MB sur le volume actuel (largement suffisant pour usage solo)

**Q: Et si je dépasse 500 MB ?**
A: Tu peux agrandir le volume dans Railway Dashboard (facturation au GB utilisé)

---

**Créé le** : 2025-01-06
**Système** : Railway Volumes + DataManager
**Usage** : Solo (optimisé pour 1 utilisateur)
