# Décisions techniques et alternatives

Critère 16 : justification (3 pts) et alternative proposée (3 pts). Toute justification s'appuie
sur nos contraintes réelles : **Ollama local, Python sans framework LLM, PC sans gros GPU**, et
jamais sur « on connaissait déjà ».

## Features volontairement non implémentées

| Feature                       | Pourquoi on l'a exclue (architecture et scénario)                                                                                                                                                          |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A2 Multi-agents**           | Chaque agent = un appel modèle de plus. Sur CPU à ~15 tok/s, trois agents en série triplent une latence déjà de 10 à 30 s. Les besoins de Karim (chercher, rédiger) tiennent dans une boucle ReAct unique. |
| **R2 RAG avancé (reranking)** | Un reranker est un second modèle à charger et à appeler sur chaque chunk : RAM et latence en plus pour un corpus de quelques dizaines de pages, où la recherche cosinus suffit.                            |
| **Assistant vocal en cabine** | Hors scope pour la sécurité (conduite) et incompatible avec la latence CPU.                                                                                                                                |
| **X5 Planification**          | Pas de besoin : les tournées sont planifiées dans l'outil métier existant, pas dans l'assistant.                                                                                                           |

Présent dans le code mais hors scénario (à assumer) : sandbox Python (T2), MCP (T1), Groq. Ils
prouvent l'extensibilité de l'architecture, pas un besoin de Karim. La sandbox peut se justifier
pour les calculs (les petits modèles se trompent en arithmétique), Groq est à désactiver pour
raisons RGPD.

## Décisions majeures et arbitrages

### 1. Base vectorielle : SQLite + cosinus

| Alternative             | Raison du choix ou du rejet                                                                              |
| ----------------------- | -------------------------------------------------------------------------------------------------------- |
| ChromaDB, Qdrant        | Service ou dépendance lourde de plus ; Qdrant demande un serveur. Corpus de quelques centaines de chunks |
| FAISS                   | Index approximatif utile au-delà de ~100 000 vecteurs ; pas notre échelle                                |
| `sqlite-vec`            | Bonne option, extension C à charger : moins portable sur les postes Windows d'une collectivité           |
| **SQLite + cosinus** ✅ | `sqlite3` dans la stdlib, un seul fichier, zéro service ; produit scalaire en C                          |

**Arbitrage** : déploiement simple contre recherche linéaire. `SQLiteVectorStore.search` parcourt
les vecteurs, calcule le produit scalaire en C et ne charge le texte que des meilleurs résultats :
30 ms pour 1 000 chunks sur le PC mesuré ([benchmarks](../benchmarks.md#sensais-own-code)).

### 2. Taille des chunks : 500 caractères, chevauchement 50, top 5

**Contraintes contradictoires** : granularité vs coût de contexte.

- Plus petit (200) : recherche précise, mais une règle de sécurité coupée en deux perd son sens.
- Plus grand (2000) : contexte complet, mais 5 chunks ≈ 2 500 tokens, ce qui remplit un `num_ctx`
  de 4096 et allonge le temps avant le premier token.
- **500 × 5 ≈ 600 tokens** : tient dans le budget avec l'historique, au prix de chunks parfois coupés
  au milieu d'une phrase (découpe par caractères, pas par paragraphe).

À mesurer avec le bench (exactitude pour 300 / 500 / 1000) pour transformer ce choix en donnée.

### 3. Comptage de tokens : estimation à 4 caractères par token

**Arbitrage** : vitesse et zéro dépendance contre précision. Un tokenizer exact demande soit la
bibliothèque du modèle (lourde, propre à chaque famille), soit un appel à Ollama par message.
L'estimation sert seulement à déclencher la compression avant la limite ; une marge
(`threshold = 0.8`) absorbe l'erreur. Limite : le français et le code font en moyenne moins de 4
caractères par token, donc on sous-estime le nombre réel de tokens.

### 4. Guardrails par regex + checksums plutôt qu'un modèle classifieur

**Arbitrage** : latence et déterminisme contre couverture. Un classifieur (Llama Guard, NER) ajoute
un appel modèle par message et par chunk de réponse, impossible à tenir en streaming sur CPU. Les
regex + Luhn / mod-97 / clé NIR sont instantanées, testables (corpus EV4) et sans faux positifs sur
les numéros invalides. Prix : noms, adresses et paraphrases passent (documenté en `known_gap`).

### 5. Format de mémoire : faits structurés en SQLite (M3) plutôt que mémoire vectorielle

Des faits `entité.clé = valeur` sont lisibles, modifiables par `/memory`, et l'utilisateur voit
exactement ce qui est retenu (transparence RGPD). Une mémoire vectorielle des conversations
retrouverait plus de choses, mais opaque et impossible à corriger précisément.

### 6. Pas de framework LLM

Imposé par le sujet, mais aussi utile : le pipeline complet tient dans `core/engine.py`,
`core/streaming.py` et `core/tool_runner.py`, et nous a obligés à comprendre le format d'outils
d'Ollama, le streaming NDJSON et le découpage des PII entre chunks.

### 7. Modèle principal : Qwen 3.5 4B

Nous retenons `qwen3.5:4b` pour son compromis entre appels d’outils, exploitation des documents
et coût matériel. Il réussit les six actions d’outils réellement exécutées, sans appel inutile
sur les quatre questions simples. Il obtient également 19/22 au benchmark automatique RAG avec
persona. Sur la machine d’Alban, son débit atteint 37 tokens/s sur GPU et 11 tokens/s sur CPU.
Les essais d’exécution et de qualité ont été réalisés séparément sur la RTX 4070 ;
les [protocoles et résultats](../benchmarks.md#ticket-83-live-tool-execution-on-the-six-requested-models)
distinguent ces mesures des débits historiques d’Alban sur RTX 4060.

Llama 3.2 exécute aussi les six actions, mais appelle inutilement des outils sur les quatre
questions simples. Mistral et Phi n’exécutent aucune des six actions ; Gemma 3 ne prend pas en
charge les outils natifs dans Ollama. Gemma 4 reste une alternative plus rapide, avec 10/10 au
test de choix d’outils et 18/22 au benchmark RAG, mais sans validation équivalente sur les 35 cas
de démo.

Ce choix ne garantit pas la fiabilité des réponses. Qwen peut inventer après un résultat
d’outil correct, manquer une information présente dans le corpus ou mal respecter une consigne.
Le score RAG repose sur des mots-clés, sans vérifier toutes les affirmations ni les citations.
Les [résultats des 35 cas](prompts-de-test.md) documentent ces limites ; les écritures restent
soumises à confirmation et les réponses sensibles doivent être vérifiées.

## Alternatives : si c'était à refaire

Chaque proposition résout un goulot identifié et reste dans les règles (Ollama local, sans
LangChain, notre matériel).

| Alternative                                                                                    | Goulot résolu                                                                   | Réaliste ?                                          |
| ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------- |
| **Fixer le scénario en semaine 1**, puis choisir les features                                  | Features construites sans besoin (MCP, sandbox) ; jeu de données arrivé tard    | Organisationnel, coût nul                           |
| **Envoyer `options` (`num_ctx`, `temperature`, `seed`) dès le MVP**                            | Troncature silencieuse du prompt par Ollama, benchmarks non rejouables          | Quelques lignes dans le provider                    |
| **Compter les tokens avec les champs d'Ollama** (`prompt_eval_count`) et calibrer l'estimation | Estimation fausse en français                                                   | Champs déjà renvoyés par l'API                      |
| **Découpage RAG par paragraphe/titre Markdown** au lieu de caractères                          | Règles coupées en deux, sources moins citables                                  | Pur Python                                          |
| **`sqlite-vec`** pour la recherche vectorielle                                                 | Recherche linéaire si le corpus grossit                                         | Extension SQLite, reste local                       |
| **Prompt caching via `keep_alive` + préfixe système stable**                                   | Temps avant le premier token : le prefill est recalculé quand le préfixe change | Ollama réutilise le cache KV d'un préfixe identique |
| **Bench A/B écrit en même temps que chaque feature**                                           | Améliorations non prouvées en fin de projet                                     | Réutilise `build_session` et le juge EV1            |
| **Logger structuré unique (prompt, tokens, durées) dès le début**                              | Débogage à l'aveugle des réponses du modèle                                     | stdlib `logging` + JSONL                            |
