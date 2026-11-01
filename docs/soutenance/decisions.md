# Décisions techniques et alternatives

Critère 16 : justification (3 pts) et alternative proposée (3 pts). Toute justification s'appuie
sur nos contraintes réelles : **Ollama local, Python sans framework LLM, PC sans gros GPU**, et
jamais sur « on connaissait déjà ».

## Features volontairement non implémentées

| Feature                       | Pourquoi on l'a exclue (architecture et scénario)                                                                                                                                                            |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **A2 Multi-agents**           | Chaque agent = un appel modèle de plus. Sur CPU à ~15 tok/s, trois agents en série triplent une latence déjà de 10 à 30 s. Les besoins de Camille (chercher, rédiger) tiennent dans une boucle ReAct unique. |
| **R2 RAG avancé (reranking)** | Un reranker est un second modèle à charger et à appeler sur chaque chunk : RAM et latence en plus pour un corpus de quelques dizaines de pages, où la recherche cosinus suffit.                              |
| **Assistant vocal en cabine** | Hors scope pour la sécurité (conduite) et incompatible avec la latence CPU.                                                                                                                                  |
| **X5 Planification**          | Pas de besoin : les tournées sont planifiées dans l'outil métier existant, pas dans l'assistant.                                                                                                             |

Présent dans le code mais hors scénario (à assumer) : sandbox Python (T2), MCP (T1), Groq. Ils
prouvent l'extensibilité de l'architecture, pas un besoin de Camille. La sandbox peut se justifier
pour les calculs (les petits modèles se trompent en arithmétique), Groq est à désactiver pour
raisons RGPD.

## Pivots : features modifiées ou retirées en cours de route

Chaque ligne pointe vers le commit qui le prouve (`git show <hash>`).

| Date  | Changement                                                                                                        | Pourquoi                                                                                                                                       | Impact sur le scope                                                                                           | Commit               |
| ----- | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------- |
| 30/09 | Modèle par défaut : `llama3.2:3b` → `qwen3.5:4b`                                                                  | Llama 3.2 3B inventait le contenu d'un fichier après l'avoir lu avec l'outil ; Qwen appelle les outils de façon fiable et parle mieux français | +0,5 Go de RAM ; `ollama/Modelfile` gardé pour qui reste sur Llama                                            | `fe3df51`            |
| 06/10 | Confirmation des outils (HITL) : fenêtre modale TUI et `y/n` CLI → question en bas d'écran et sélecteur à flèches | Répondre sans quitter le fil : la question s'affiche sous la conversation au lieu de la recouvrir                                              | Même garde-fou, moins de clics ; tests de confirmation réécrits                                               | `bf4acfc`, `5adfc98` |
| 12/10 | Ajout du provider Groq (API cloud)                                                                                | Démontrer l'interchangeabilité des providers et offrir une option rapide aux postes sans GPU                                                   | **Sorti du scénario ensuite** : données d'usagers hors UE (RGPD). Gardé dans le code, désactivé pour Karim    | `116267e`            |
| 14/10 | Interface web en plus de la CLI et de la TUI                                                                      | La persona (chef d'équipe, pas développeur) n'est pas à l'aise dans un terminal                                                                | Dépendances `fastapi` + `uvicorn` ; la CLI reste l'interface du MVP et des tests                              | `95cc5e3`            |
| 19/10 | Scénario « Sensai Collecte » fixé, persona et corpus métier ajoutés                                               | Retour de soutenance : features montrées dans l'ordre du catalogue, sans utilisateur                                                           | MCP, sandbox et Groq deviennent hors scénario (voir plus haut) ; RAG et mémoire recentrés sur la collecte     | `f9b9160`, `10e7603` |
| 19/10 | Interrupteurs `enabled` pour RAG, recherche web et sandbox dans `sensai.toml`                                     | Retour de soutenance : impossible de couper une feature sans toucher au code                                                                   | Toute feature se coupe par config ou `/config set`, l'outil disparaît du prompt                               | `db2d0ee`            |
| 19/10 | Options du modèle (`temperature`, `seed`, `num_ctx`…) envoyées à Ollama                                           | Avant, Ollama utilisait ses valeurs par défaut : benchmarks non rejouables, réglages invisibles                                                | `[options]` dans la config, validées                                                                          | `d3d087d`            |
| 21/10 | `num_ctx = 8192` par défaut                                                                                       | Prouvé par le bench `context` : sans lui, Ollama coupe le début du prompt à 4 096 tokens, donc la persona et les règles                        | Cache KV un peu plus gros (32k ne coûte que 1,1 Go de plus que 2k) ; le budget M2 est validé contre `num_ctx` | `886e662`            |
| 21/10 | Vecteurs RAG en JSON → binaire compacté + produit scalaire en C                                                   | 232 ms par recherche sur 1 000 chunks                                                                                                          | 30 ms ; base à réindexer                                                                                      | `17cb37f`            |
| 26/10 | Réflexion (`/effort`) : `low` reste le défaut, mais `off` recommandé pour la démo                                 | Bench `effort` : 50 s de réflexion pour une addition que le mode `off` résout juste en 3 s ; `low`, `medium` et `high` donnent la même chose   | Le mode réflexion n'est plus présenté comme un gain, seulement comme un réglage ; à passer à `off` par défaut | `6b833a0`            |

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

### 8. Décisions mesurées en répétant la démo (1er novembre)

Trois problèmes trouvés en jouant le script sur le PC de démo, chacun corrigé avec une mesure avant et
après. Ce sont de bons exemples d'« amélioration mesurée » à raconter au jury.

| Problème constaté                                                                | Mesure avant                                                    | Correction                                                                 | Mesure après                                                      |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Raisonnement coupé, mais qwen3.5 réfléchit quand même (`thinking.default: true`) | **540 s** pour une question, 4 073 tokens de réflexion cachée   | Sensai envoie `think: false` quand `[reasoning] enabled = false`           | **3,9 s**                                                         |
| `nomic-embed-text` (anglais) ne retrouve pas nos documents français              | Calendrier au rang 10, plan hivernal au rang 15 (sur 26 chunks) | `bge-m3`, modèle d'embedding multilingue, et `top_k = 3`                   | Calendrier au rang 2, plan hivernal au rang 1 ; prompt plus court |
| Le modèle 4B lit mal un tableau Markdown (colonne voisine)                       | « bac jaune le mardi et le vendredi » (colonne du bac marron)   | Calendrier réécrit en une phrase par secteur dans `calendrier-secteurs.md` | « le mercredi », correct                                          |

Écarté : réordonner le prompt pour profiter du cache d'Ollama. Mesuré : avec qwen3.5 sur CPU, le cache
ne sert que si la requête prolonge exactement la précédente (cas des appels d'outils dans un même tour),
pas d'un tour à l'autre.

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
