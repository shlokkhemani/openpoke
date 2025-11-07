# Fonctionnalités Avancées de Recherche avec Composio

## Vue d'ensemble

Grâce à Composio, nous avons maintenant accès à **8 outils de recherche puissants** au lieu de juste la recherche web basique. Cela transforme l'agent de recherche en un véritable assistant de recherche intelligent.

## Outils Disponibles

### 🔍 Recherche de Base (5 outils)

#### 1. **`search_web`**
Recherche web générale avec filtrage de domaines.

```json
{
  "query": "quantum computing breakthroughs 2025",
  "num_results": 10,
  "include_domains": ["nature.com", "science.org"]
}
```

#### 2. **`search_news`**
Recherche d'actualités via 12 sources fiables (NYT, WSJ, Reuters, Bloomberg, etc.).

```json
{
  "query": "artificial intelligence regulation",
  "num_results": 15
}
```

#### 3. **`research_topic`**
Recherche multi-facettes avec focus areas.

```json
{
  "topic": "climate change",
  "focus_areas": ["impact", "solutions", "policy"],
  "num_results": 12
}
```

#### 4. **`search_company`**
Recherche complète sur une entreprise.

```json
{
  "company_name": "Tesla",
  "aspects": ["news", "financials", "products"],
  "num_results": 10
}
```

#### 5. **`search_academic`**
Sources académiques et scientifiques.

```json
{
  "query": "neural network architectures",
  "num_results": 10
}
```

---

### 🚀 Outils Avancés Composio (3 nouveaux outils)

#### 6. **`answer_question`** ⭐ LE PLUS PUISSANT

**Génère une réponse directe avec citations** au lieu de juste retourner des résultats.

**Utilise l'IA d'Exa** pour synthétiser une réponse à partir de multiples sources.

```json
{
  "question": "What are the main challenges in quantum computing?",
  "num_sources": 5,
  "include_domains": ["nature.com", "science.org"]
}
```

**Résultat** :
```json
{
  "question": "What are the main challenges...",
  "answer": "The main challenges in quantum computing include:\n1. Decoherence and quantum noise...\n2. Scalability of qubit systems...\n3. Error correction...",
  "citations": [
    {
      "url": "https://nature.com/articles/...",
      "title": "Quantum Computing Challenges",
      "snippet": "..."
    },
    ...
  ]
}
```

**Quand l'utiliser** :
- ✅ Questions complexes nécessitant une synthèse
- ✅ Besoin d'une réponse directe plutôt que des liens
- ✅ Recherche d'expert sur un sujet
- ✅ Comparaisons et analyses

**Exemples d'usage** :
- "What are the differences between React and Vue?"
- "Explain how blockchain consensus mechanisms work"
- "What causes inflation and how do central banks control it?"

---

#### 7. **`find_similar_content`**

**Recherche sémantique par URL** - trouve des contenus similaires via embeddings.

```json
{
  "url": "https://example.com/article-about-ai",
  "num_results": 10,
  "include_full_content": true
}
```

**Résultat** :
```json
{
  "reference_url": "https://example.com/...",
  "results": [
    {
      "url": "https://related-article-1.com",
      "title": "Similar AI Article",
      "score": 0.92,
      "text": "Full content..." // si include_full_content=true
    },
    ...
  ],
  "total_results": 10
}
```

**Quand l'utiliser** :
- ✅ Trouver des articles similaires
- ✅ Exploration de contenu connexe
- ✅ Veille concurrentielle (produits similaires)
- ✅ Recommandations de lecture

**Exemples d'usage** :
- "Find articles similar to this one: [URL]"
- "Show me products like this one: [URL]"
- "What other blogs cover similar topics to [URL]?"

---

#### 8. **`extract_content`**

**Extrait le contenu complet** d'une liste d'URLs (max 10).

```json
{
  "urls": [
    "https://example.com/article1",
    "https://example.com/article2"
  ],
  "include_highlights": true
}
```

**Résultat** :
```json
{
  "urls": ["https://example.com/article1", ...],
  "contents": [
    {
      "url": "https://example.com/article1",
      "title": "Article Title",
      "text": "Full article content...",
      "highlights": ["Key point 1", "Key point 2"] // si include_highlights=true
    },
    ...
  ],
  "total_retrieved": 2
}
```

**Quand l'utiliser** :
- ✅ Lecture approfondie de plusieurs articles
- ✅ Analyse de contenu complet
- ✅ Extraction de données structurées
- ✅ Recherche documentaire

**Exemples d'usage** :
- "Read these 3 articles and summarize them: [URLs]"
- "Extract the main points from these sources: [URLs]"
- "Get full text of these search results: [URLs]"

---

## Workflows Intelligents

### Workflow 1 : Question Complexe → Réponse Directe

```
User: "How does photosynthesis work?"
                ↓
Agent: answer_question("How does photosynthesis work?")
                ↓
Résultat: Réponse synthétisée + 5 citations
```

**Avant** (search_web) : 10 liens à lire
**Après** (answer_question) : Réponse directe avec sources ✅

---

### Workflow 2 : Recherche → Approfondissement

```
User: "Find articles about AI safety"
                ↓
Agent: search_web("AI safety", num_results=5)
                ↓
User sélectionne un article intéressant
                ↓
Agent: find_similar_content(selected_url)
                ↓
Agent: extract_content([similar_urls])
                ↓
Analyse complète du sujet
```

---

### Workflow 3 : Recherche Exhaustive

```
User: "Research everything about Tesla's new battery technology"
                ↓
1. answer_question("What is Tesla's latest battery technology?")
   → Réponse synthétisée
                ↓
2. search_company("Tesla", aspects=["products", "news"])
   → Actualités et produits
                ↓
3. search_academic("Tesla battery technology")
   → Sources scientifiques
                ↓
4. extract_content([selected_urls])
   → Lecture approfondie
                ↓
Rapport complet avec sources multiples
```

---

## Comparaison des Outils

| Outil | Cas d'usage | Sortie | Latence |
|-------|-------------|--------|---------|
| `search_web` | Recherche générale | Liste de liens | ~1-2s |
| `search_news` | Actualités récentes | Liste d'articles news | ~1-2s |
| `research_topic` | Recherche multi-facettes | Résultats par aspect | ~3-6s |
| `search_company` | Info entreprise | Résultats par catégorie | ~2-4s |
| `search_academic` | Sources scientifiques | Papers académiques | ~1-2s |
| `answer_question` ⭐ | Réponse directe | Texte + citations | ~2-4s |
| `find_similar_content` | Similarité sémantique | Pages similaires | ~1-3s |
| `extract_content` | Extraction complète | Texte intégral | ~2-5s |

---

## Architecture Technique

### Services

```python
# Service basique (MCP - pour compatibilité)
services/search/exa.py
    ↓
def search_exa(query, num_results, include_domains, exclude_domains)
```

```python
# Service avancé (Native Exa SDK) ⭐
services/search/composio_exa.py
    ↓
def generate_answer(query, num_results, ...) → Answer + Citations
def find_similar(url, num_results) → Similar Pages
def get_contents(urls) → Full Content
def advanced_search(query, date_filters, category) → Advanced Results
```

### Pattern Native Exa SDK

Les outils avancés utilisent le **SDK Exa natif** (exa_py) :

```python
# Singleton client thread-safe
_CLIENT_LOCK = threading.Lock()
_CLIENT: Optional[Any] = None

def _get_exa_client(settings: Optional[Any] = None):
    """Get or create singleton Exa client."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    with _CLIENT_LOCK:
        if _CLIENT is None:
            from exa_py import Exa
            api_key = settings.exa_api_key
            _CLIENT = Exa(api_key=api_key)
    return _CLIENT

# Appels directs via SDK
client = _get_exa_client()
result = client.search_and_contents(query, num_results=5, text=True)
result = client.find_similar(url, num_results=10)
result = client.get_contents(urls, text=True)
```

**Avantages du SDK natif** :
- ✅ Plus rapide (pas de couche HTTP MCP)
- ✅ Plus fiable (moins de points de défaillance)
- ✅ Meilleure documentation (Exa officielle)
- ✅ Plus de contrôle sur les paramètres
- ✅ Mêmes patterns que Gmail (singleton thread-safe)

---

## Configuration

Configuration simple avec le SDK Exa natif :

```bash
# Variable requise pour les outils avancés
EXA_API_KEY=your_exa_api_key_here

# Variables MCP (pour search_web basique uniquement)
COMPOSIO_EXA_MCP_URL=https://backend.composio.dev/v3/mcp/.../mcp?user_id=exa
COMPOSIO_API_KEY=ak_...
```

**Note** : Les outils avancés (answer_question, find_similar, extract_content) nécessitent uniquement `EXA_API_KEY`. Le search_web basique continue d'utiliser le MCP.

---

## Impact sur l'Expérience Utilisateur

### Avant
```
User: "What are the main challenges in quantum computing?"
Agent: [Retourne 10 liens]
User: *doit lire 10 articles lui-même*
```

### Après
```
User: "What are the main challenges in quantum computing?"
Agent: [Appelle answer_question()]
Agent: "The main challenges include:
       1. Decoherence and quantum noise...
       2. Scalability of qubit systems...
       3. Error correction...

       Sources: [3 citations académiques]"
User: ✅ Réponse immédiate et sourcée
```

---

## Logging & Observabilité

Tous les nouveaux outils incluent le même logging que les outils existants :

```python
# Succès
"answer_question succeeded | query='quantum challenges' | results=5"

# Échec
"find_similar_content failed | url='...' | error=MCP unavailable"
```

---

## Limites & Bonnes Pratiques

### Limites
- `extract_content` : Max 10 URLs par appel
- `answer_question` : Max 20 sources
- `find_similar` : Max 20 résultats

### Bonnes Pratiques

1. **Utiliser `answer_question` pour les questions complexes**
   ```python
   # ✅ Bon
   answer_question("How does X work?")

   # ❌ Moins optimal
   search_web("how does X work") → User lit tout lui-même
   ```

2. **Chaîner les outils intelligemment**
   ```python
   # Workflow intelligent
   results = search_web("AI safety")
   similar = find_similar_content(results[0]['url'])
   content = extract_content([s['url'] for s in similar[:3]])
   ```

3. **Préférer les domaines de confiance pour `answer_question`**
   ```python
   answer_question(
       "latest cancer research",
       include_domains=["nature.com", "science.org", "pubmed.gov"]
   )
   ```

---

## Prochaines Évolutions

### Possibles
1. **Cache intelligent** : Éviter les recherches identiques
2. **Recherche multi-langues** : Support i18n
3. **Websets** : Collections personnalisées (Composio supporte déjà)
4. **Monitors** : Alertes automatiques sur nouveaux contenus

---

## Conclusion

Avec Composio, l'agent de recherche passe de **"moteur de recherche"** à **"assistant de recherche intelligent"** :

- 🔍 **5 outils** de recherche spécialisée (web, news, academic, company, topic)
- 🚀 **3 outils** avancés Composio (answer, similar, extract)
- 📊 **Total : 8 outils** vs 1 avant
- ⭐ **`answer_question`** : Game changer pour questions complexes
- 🔗 **Architecture propre** : Suit les mêmes patterns que Gmail
- 📝 **Logging complet** : Observabilité totale

L'utilisateur peut maintenant obtenir des **réponses directes** au lieu de juste des liens ! 🎯

