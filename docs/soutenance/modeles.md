# Modèles : culture IA et choix

Réponses préparées pour le critère 7 (4 pts, 1 pt par point validé) et tableau de nos mesures.

## Paramètres et empreinte mémoire

**Question jury** : « C'est quoi un paramètre dans un Transformer ? Quelle différence entre un 7B
et un 70B sur nos machines ? »

Un **paramètre** est un nombre appris pendant l'entraînement : un poids (l'équivalent d'un poids
synaptique, la force d'une connexion entre deux neurones artificiels) ou un biais. Dans un
Transformer ils se trouvent dans :

- la table d'embedding (un vecteur par token du vocabulaire) ;
- les matrices d'attention de chaque couche (Q, K, V, sortie) ;
- les MLP de chaque couche (environ deux tiers des paramètres) ;
- les normalisations et la tête de sortie.

« 7B » = 7 milliards de ces nombres. Plus de paramètres = plus de connaissances et de capacité de
raisonnement mémorisées, mais plus de mémoire et moins de vitesse.

**Empreinte théorique des poids** = paramètres × octets par paramètre :

| Précision   | Octets/param     | 4B     | 7B     | 70B    |
| ----------- | ---------------- | ------ | ------ | ------ |
| FP32        | 4                | 16 Go  | 28 Go  | 280 Go |
| FP16 / BF16 | 2                | 8 Go   | 14 Go  | 140 Go |
| Q8_0        | ~1,06            | 4,3 Go | 7,5 Go | 75 Go  |
| Q4_K_M      | ~0,6 (≈4,8 bits) | 2,5 Go | 4,3 Go | 42 Go  |

**Sur nos machines** (32 Go de RAM, pas de gros GPU) :

- 4B en Q4 : tient largement, ~10 à 25 tok/s sur CPU.
- 7B en Q4 : tient, environ deux fois plus lent que le 4B (deux fois plus d'octets lus par token).
- 70B en Q4 : 42 Go de poids, **ne tient pas** dans 32 Go. Même sur une machine à 64 Go, ~1 tok/s
  sur CPU : une réponse de 200 tokens prend plus de 3 minutes. Inutilisable pour Karim.

Compromis : le 70B raisonne mieux, suit mieux les consignes et hallucine moins, mais le temps de
réponse sort du cadre du scénario ([scenario.md](scenario.md#cohérence-avec-la-latence-locale)).

### Cache KV et taille du contexte

En plus des poids, le modèle garde pour chaque token du contexte ses clés et valeurs d'attention :

```text
cache KV = 2 (K et V) × couches × têtes KV × dimension par tête × num_ctx × octets
```

Exemple Llama 3.1 8B (32 couches, 8 têtes KV grâce au GQA, dimension 128, FP16) :
`2 × 32 × 8 × 128 × 2 octets = 128 Kio par token` → 8192 tokens = 1 Gio, 128k tokens = 16 Gio.
C'est pour ça qu'augmenter `num_ctx` augmente la RAM et que la fenêtre native maximale n'est pas
utilisable telle quelle sur un PC.

## Quantification

**Question jury** : « Q4_K_M vs FP16 : impact sur la mémoire, le débit et la qualité ? »

La quantification **réduit la précision numérique** des poids : chaque poids FP16 (16 bits) est
remplacé par un entier de 8, 5 ou 4 bits, plus un facteur d'échelle partagé par bloc de poids.

- **Q4_K_M** (format GGUF de llama.cpp, utilisé par Ollama) : blocs de poids en 4 bits avec
  échelles quantifiées (« K-quants ») ; « M » = mix moyen, certaines couches sensibles (une partie
  de l'attention et du MLP) gardées en 6 bits. Environ 4,8 bits par poids en moyenne.
- **Mémoire** : ~3,3× plus petit que FP16 (14 Go → 4,3 Go pour un 7B).
- **Débit** : la génération est limitée par la bande passante mémoire ; 3,3× moins d'octets à lire
  par token = génération proche de 3× plus rapide (voir [observabilite.md](observabilite.md#débit-tokenss)).
- **Qualité** : perte de **perplexité** marginale en Q8 et Q5_K_M (quelques pourcents de hausse),
  encore faible en Q4_K_M, nette en dessous (Q3, Q2). Les petits modèles souffrent plus de la
  quantification que les gros : un 70B en Q4 reste meilleur qu'un 7B en FP16.

Règle pratique : **le plus gros modèle qui tient en mémoire en Q4_K_M** bat un modèle plus petit en
haute précision.

À vérifier : `ollama show qwen3.5:4b` affiche la quantification et la fenêtre de contexte native.

## Familles de modèles

**Question jury** : « Pourquoi votre modèle plutôt qu'un autre (Llama, Mistral, Qwen, Gemma, Phi) ? »

| Famille   | Éditeur         | Forces                                                                                                       | Faiblesses pour nous                                                                   |
| --------- | --------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| Llama 3.x | Meta            | Écosystème énorme, fenêtre 128k, tool calling                                                                | 3B : invente après un résultat d'outil (constaté, voir README) ; licence communautaire |
| Mistral   | Mistral AI (FR) | Bon en français et langues européennes, Nemo 12B avec 128k                                                   | Petits modèles moins bons en appel d'outils ; 7B déjà ancien                           |
| Qwen      | Alibaba         | Très bon multilingue (français inclus), appels d'outils fiables même en petit, mode « thinking », Apache 2.0 | Biais de l'entraînement chinois sur certains sujets                                    |
| Gemma 3   | Google          | Multimodal, fenêtre 128k (4B et plus), bonne qualité de texte                                                | Pas de rôle `tool` natif, tool calling moins robuste                                   |
| Phi       | Microsoft       | Raisonnement et maths très bons pour la taille                                                               | Multilingue et connaissances générales plus faibles                                    |

**Notre choix : `qwen3.5:4b`**, argumenté par nos contraintes et pas par habitude :

1. **Tool calling fiable à 4B** : nos features clés (fichiers, mémoire, rapport d'incident) reposent
   sur des appels d'outils. Llama 3.2 3B inventait le contenu après avoir lu un fichier ; il a fallu
   un Modelfile spécial (`ollama/Modelfile`) pour le cadrer.
2. **Français** : utilisateurs francophones (Karim, Léa).
3. **Taille** : 4B en Q4 tient sur un PC de dépôt sans GPU avec un débit compatible du scénario.
4. **Raisonnement réglable** : `think` (`/effort`) permet d'arbitrer qualité contre latence en direct.
5. **Licence Apache 2.0** : déploiement possible dans une collectivité sans contrainte de licence.

Tests qui le prouvent : `SENSAI_OLLAMA_TEST_MODEL=qwen3.5:4b uv run pytest tests/providers/test_ollama.py -k live`.

## Génératif vs embedding

**Question jury** : « Différence fondamentale d'architecture et d'usage ? »

| Aspect         | Modèle génératif (`qwen3.5:4b`)                                          | Modèle d'embedding (`nomic-embed-text`)                                          |
| -------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| Architecture   | **Décodeur** seul, attention **causale** (un token ne voit que le passé) | **Encodeur**, attention **bidirectionnelle** (chaque token voit toute la phrase) |
| Sortie         | Distribution de probabilité sur le prochain token                        | Un **vecteur dense** de taille fixe (768 dimensions pour nomic)                  |
| Fonctionnement | **Autorégressif** : génère token par token, chaque token réinjecté       | Une seule passe, puis **pooling** (moyenne des vecteurs de tokens)               |
| Usage          | Répondre, rédiger, appeler des outils                                    | Mesurer la **similarité sémantique** (cosinus) entre textes                      |
| Coût           | Proportionnel au nombre de tokens générés                                | Une passe par texte, très rapide                                                 |
| Dans Sensai    | `OllamaLLMProvider`, `/api/chat`                                         | `OllamaEmbeddingProvider`, `/api/embed`                                          |

Dans notre RAG (`memory/rag/`) : chaque chunk de 500 caractères est transformé en vecteur à
l'indexation, la question aussi à chaque tour, `SQLiteVectorStore.search` calcule le cosinus et
renvoie les 5 meilleurs chunks, qui sont injectés dans le prompt du modèle génératif.

On ne peut pas utiliser le génératif pour l'embedding efficacement (vecteurs non entraînés pour la
similarité, modèle 10× plus gros), ni l'embedding pour générer (pas de tête de prédiction).

## Tableau des modèles testés

À remplir avec les mesures de [benchmarks.md](benchmarks.md) et [observabilite.md](observabilite.md).
Même machine, même prompt, `temperature = 0`, `seed = 42`.

| Modèle           | Taille | Quantif. | RAM (`ollama ps`) | Decode tok/s | 1er token | Tool calls OK (live tests) | Exactitude RAG (bench) | Français | Retenu |
| ---------------- | ------ | -------- | ----------------- | ------------ | --------- | -------------------------- | ---------------------- | -------- | ------ |
| qwen3.5:4b       | 4B     |          |                   |              |           |                            |                        |          | ✅     |
| llama3.2 (3B)    | 3B     |          |                   |              |           |                            |                        |          |        |
| sensai-llama3.2  | 3B     |          |                   |              |           |                            |                        |          |        |
| mistral (7B)     | 7B     |          |                   |              |           |                            |                        |          |        |
| gemma3:4b        | 4B     |          |                   |              |           |                            |                        |          |        |
| phi4-mini        | 3,8B   |          |                   |              |           |                            |                        |          |        |
| nomic-embed-text | 137M   |          |                   | n/a          | n/a       | n/a                        | (embedding)            | n/a      | ✅     |
