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
- les MLP de chaque couche (environ deux tiers des paramètres dans certains Transformers denses) ;
- les normalisations et la tête de sortie.

« 7B » = 7 milliards de ces nombres. Plus de paramètres augmente généralement la capacité,
mais ne garantit pas davantage de connaissances exactes ni un meilleur raisonnement. Le coût
en mémoire et en calcul augmente aussi ; le débit dépend notamment de l’architecture et du matériel.

**Empreinte théorique des poids** = paramètres × octets par paramètre :

| Précision   | Octets/param     | 4B     | 7B     | 70B    |
| ----------- | ---------------- | ------ | ------ | ------ |
| FP32        | 4                | 16 Go  | 28 Go  | 280 Go |
| FP16 / BF16 | 2                | 8 Go   | 14 Go  | 140 Go |
| Q8_0        | ~1,06            | 4,3 Go | 7,5 Go | 75 Go  |
| Q4_K_M      | ~0,6 (≈4,8 bits) | 2,5 Go | 4,3 Go | 42 Go  |

**Sur le PC mesuré d’Alban** (16 Go de RAM, RTX 4060 8 Go) :

- 4B en Q4 : tient en mémoire ; `qwen3.5:4b` atteint 11 tok/s sur CPU et 37 tok/s sur GPU.
- 7B en Q4 : tient aussi ; `mistral:7b` atteint 7,6 tok/s sur CPU et 23 tok/s sur GPU.
- 70B en Q4 : environ 42 Go de poids, **ne tient pas** dans 16 ou 32 Go de RAM, ni dans
  8 Go de VRAM. Sur une machine de 64 Go, le débit reste à mesurer : on ne peut pas le déduire
  du seul nombre de paramètres.

Compromis : un modèle plus gros peut améliorer certaines réponses, mais il faut le vérifier à
qualité et latence mesurées. Ce 70B sort du matériel prévu pour le scénario
([scenario.md](scenario.md#cohérence-avec-la-latence-locale)).

### Cache KV et taille du contexte

En plus des poids, le modèle garde pour chaque token du contexte ses clés et valeurs d'attention :

```text
cache KV = 2 (K et V) × couches × têtes KV × dimension par tête × num_ctx × octets
```

Exemple Llama 3.1 8B (32 couches, 8 têtes KV grâce au GQA, dimension 128, FP16) :
`2 × 32 × 8 × 128 × 2 octets = 128 Kio par token` → 8192 tokens = 1 Gio, 128k tokens = 16 Gio.
C'est pour ça qu'augmenter `num_ctx` augmente la RAM et que la fenêtre native maximale n'est pas
toujours utilisable telle quelle sur un PC disposant de peu de mémoire.

## Quantification

**Question jury** : « Q4_K_M vs FP16 : impact sur la mémoire, le débit et la qualité ? »

La quantification **réduit la précision numérique** des poids : chaque poids FP16 (16 bits) est
remplacé par un entier de 8, 5 ou 4 bits, plus un facteur d'échelle partagé par bloc de poids.

- **Q4_K_M** (format GGUF de llama.cpp, utilisé par Ollama) : blocs de poids en 4 bits avec
  échelles quantifiées (« K-quants ») ; « M » = mix moyen, certaines couches sensibles (une partie
  de l'attention et du MLP) gardées en 6 bits. Environ 4,8 bits par poids en moyenne.
- **Mémoire** : ~3,3× plus petit que FP16 (14 Go → 4,3 Go pour un 7B).
- **Débit** : la génération est limitée par la bande passante mémoire ; 3,3× moins d'octets à lire
  par token peut accélérer la génération. Le gain exact dépend des noyaux de calcul, du modèle
  et du matériel ; il n’est pas automatiquement de 3× (voir [observabilite.md](observabilite.md#débit-tokenss)).
- **Qualité** : la quantification peut augmenter la **perplexité** et dégrader certaines réponses.
  L’ampleur dépend du modèle, du format et des tâches ; aucun pourcentage de perte n’est mesuré
  ici pour Q8, Q5 ou Q4. Un modèle plus gros et quantifié peut être meilleur qu’un petit en FP16,
  sans que cette supériorité soit garantie sur toutes les tâches.

Règle pratique à tester : essayer un modèle qui tient en mémoire en **Q4_K_M**, puis comparer
sa qualité et son débit aux autres candidats. La taille seule ne suffit pas à trancher.

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
4. **Raisonnement réglable** : `think` (`/effort`) permet de désactiver ou activer la réflexion.
   Sur ce Qwen, `low`, `medium` et `high` ne constituent pas trois intensités distinctes ;
   le coût de la réflexion est mesuré dans [../benchmarks.md](../benchmarks.md#thinking-effort).
5. **Licence Apache 2.0** : licence du modèle retenu, à respecter lors du déploiement.

Essai live du provider et des appels d’outils (ne valide pas à lui seul le français ou tous les
arguments ci-dessus) : `SENSAI_OLLAMA_TEST_MODEL=qwen3.5:4b uv run pytest tests/providers/test_ollama.py -k live`.

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

Dans notre RAG (`memory/rag/`) : par défaut, chaque chunk de 500 caractères est transformé en vecteur à
l'indexation, la question aussi à chaque tour, `SQLiteVectorStore.search` calcule le cosinus et
renvoie les 5 meilleurs chunks, qui sont injectés dans le prompt du modèle génératif.

Dans Sensai, les rôles sont séparés : le modèle génératif répond, le modèle d’embedding produit
les vecteurs pour la similarité. Certains modèles génératifs peuvent aussi fournir des embeddings,
mais ce n’est pas le rôle de notre `OllamaLLMProvider` ; `nomic-embed-text` ne génère pas de texte.

## Tableau des modèles testés

Mesuré sur le PC d'Alban (i7-13650HX, 16 Go, RTX 4060 8 Go), sur GPU (26/10/2026) et CPU
seul (21/10/2026), avec `temperature = 0`, `seed = 42` et réflexion désactivée. La colonne
« Mémoire » vient du passage CPU ; protocole et résultats détaillés :
[../benchmarks.md](../benchmarks.md). Le tableau couvre dix modèles ; la liste initiale de
[l'issue #83](https://github.com/Nexlein/Sensai/issues/83) en nommait six, dont deux absents ici.

| Modèle           | Taille | Quantif. | Mémoire | Écriture GPU  | Écriture CPU   | Réponse 128 tok GPU / CPU | Bon outil (10 cas)     | Retenu |
| ---------------- | ------ | -------- | ------- | ------------- | -------------- | ------------------------- | ---------------------- | ------ |
| qwen3.5:4b       | 4,2B   | Q4_K_M   | 3,1 Go  | 37 tok/s      | 11,0 tok/s     | 2,0 s / 12,9 s            | **10/10**              | ✅     |
| gemma4:e4b       | 7,5B   | Q4_K_M   | 1,8 Go  | 64 tok/s      | 16,2 tok/s     | 1,6 s / 14,4 s            | **10/10**              | plan B |
| qwen3.5:2b       | 1,9B   | Q8_0     | 2,4 Go  | 64 tok/s      | 16,0 tok/s     | 1,8 s / 10,1 s            | 9/10                   | Non    |
| ministral-3:3b   | 3,8B   | Q4_K_M   | 2,7 Go  | 44 tok/s      | 13,9 tok/s     | 2,9 s / 14,0 s            | 9/10                   | Non    |
| qwen3.5:9b       | 9,0B   | Q4_K_M   | 6,2 Go  | 20 tok/s      | 6,4 tok/s      | 4,7 s / 25,6 s            | 9/10                   | Non    |
| bonsai2 (1 bit)  | 8,2B   | Q1_0     | 1,9 Go  | 61 tok/s      | 16,7 tok/s     | 2,4 s / 34,2 s            | 9/10                   | Non    |
| llama3.2:3b      | 3,2B   | Q4_K_M   | 2,6 Go  | 49 tok/s      | 15,7 tok/s     | 2,3 s / 11,9 s            | 6/10 (outils inutiles) | Non    |
| granite3.1-moe   | 3,3B   | Q4_K_M   | 2,4 Go  | **146 tok/s** | **46,2 tok/s** | 1,0 s / 5,8 s             | 4/10 (jamais d'outil)  | Non    |
| phi4-mini        | 3,8B   | Q4_K_M   | 3,1 Go  | 38 tok/s      | 12,7 tok/s     | 2,0 s / 10,7 s            | 4/10 (jamais d'outil)  | Non    |
| mistral:7b       | 7,2B   | Q4_K_M   | 5,0 Go  | 23 tok/s      | 7,6 tok/s      | 6,2 s / 31,7 s            | 4/10 (jamais d'outil)  | Non    |
| nomic-embed-text | 137M   | F16      | 0,3 Go  | n/a           | n/a            | n/a                       | n/a (embeddings)       | ✅     |

À retenir pour l'oral : la vitesse d'écriture suit le nombre de paramètres **actifs** (granite
est un mélange d'experts, ~0,8B actifs, d'où 46 tok/s) ; un modèle plus gros (qwen3.5:9b) ne
choisit pas mieux ses outils et écrit deux fois moins vite ; trois modèles n'appellent jamais
d'outil via l'API d'Ollama. Le GPU lit le prompt 20 à 65× plus vite mais n'écrit que 3 à 4× plus
vite : la génération est limitée par la bande passante mémoire, pas par le calcul. Les scores
d'outils sont identiques sur CPU et GPU.

Le [complément du 27 octobre sur RTX 4070](../benchmarks.md#first-token-and-vram-rtx-4070-follow-up)
mesure le délai du premier token en streaming et la VRAM avec le pilote NVIDIA. Il ajoute
`sensai-llama3.2` et `gemma3:4b` pour ces deux critères. Ces mesures ont leur propre matériel,
version d'Ollama et identité de modèles ; elles complètent le tableau historique ci-dessus.
Les évaluations de qualité de ces deux modèles figurent ci-dessous.

## Complément : qualité des deux modèles ajoutés

Mesuré le 27/10/2026 sur la RTX 4070, sur les 22 questions RAG du projet et les mêmes six
exercices de français. Ce complément concerne seulement les deux modèles absents du tableau
historique d’Alban. Le [protocole, les réponses et leurs limites](../benchmarks.md#added-models-rag-and-french-quality)
permettent de vérifier ce que ces scores signifient.

| Modèle          | RAG + persona, score automatique | Faits | Refus | Réponses mentionnant `.md` | Outils                                                |
| --------------- | -------------------------------- | ----- | ----- | -------------------------- | ----------------------------------------------------- |
| sensai-llama3.2 | 17/22 (77 %)                     | 13/18 | 4/4   | 0/18                       | 9/10 ; oublie `remember_fact`                         |
| gemma3:4b       | 18/22 (82 %)                     | 14/18 | 4/4   | 14/18                      | Appels natifs non pris en charge par ce modèle Ollama |

Le score RAG est une heuristique de mots-clés et de phrases de refus ; les mentions `.md` ne
sont pas des citations vérifiées. Les deux modèles donnent notamment 13 h 00 au lieu de 5 h 30
pour le secteur A. Gemma peut aussi citer le mauvais document ou ajouter une affirmation avant
de refuser une question sans réponse.

**Français** : les six réponses de chaque modèle sont compréhensibles et la correction d’accords
est réussie. En revanche, tous deux définissent le ripeur comme un travailleur des fruits et
répondent hors sujet à la reformulation d’un message sur un bac. Llama commet une faute dans
le courrier (« vous avez sorti » sans complément) ; Gemma emploie des formulations maladroites.
Cette lecture qualitative distingue la fluidité du français de la fiabilité et du respect des consignes.

## Bilan des douze modèles

Les dix autres modèles ont désormais leurs **22 réponses RAG + persona et six exercices de
français**, en complément des deux modèles ci-dessus. [Protocole et revue détaillée](../benchmarks.md#remaining-ten-models-rag-and-french-quality).
Pour accélérer à la demande de l’utilisateur, les cinq derniers modèles n’ont pas rejoué les
conditions sans RAG et sans persona. Granite, Phi, Mistral et Bonsai ont une sortie RAG limitée
à 512 tokens ; les nombres de réponses ayant atteint cette limite sont documentés dans le protocole.

| Modèle                             | RAG + persona, score automatique | Limites observées en français générique                      | Retenu         |
| ---------------------------------- | -------------------------------- | ------------------------------------------------------------ | -------------- |
| qwen3.5:4b                         | 19/22                            | Métier mal défini ; accords et reformulation imparfaits      | Oui, principal |
| gemma4:e4b                         | 18/22                            | Métier mal défini ; bac confondu avec baccalauréat           | Plan B         |
| qwen3.5:2b                         | 17/22                            | Message hors sujet ; accords et dates altérés                | Non            |
| ministral-3:3b                     | 18/22                            | Métier mal défini ; ajouts et consignes de forme manquées    | Non            |
| qwen3.5:9b                         | 18/22                            | Métier mal défini ; cause du refus et reformulation altérées | Non            |
| Bonsai 8B Q1_0 (candidat officiel) | 19/22 (sorties bornées)          | Cinq réponses en anglais coupées ; résumé réussi             | Non            |
| llama3.2:3b                        | 17/22                            | Métier mal défini ; reformulation scolaire                   | Non            |
| granite3.1-moe                     | 15/22 (sorties bornées)          | Métier mal défini ; numéro de téléphone inventé              | Non            |
| phi4-mini                          | 16/22 (sorties bornées)          | Métier mal défini ; bennes remplacées par buses              | Non            |
| mistral:7b                         | 18/22 (sorties bornées)          | Métier mal défini ; accords et reformulation erronés         | Non            |
| sensai-llama3.2                    | 17/22                            | Métier mal défini ; reformulation hors sujet                 | Non            |
| gemma3:4b                          | 18/22                            | Métier mal défini ; reformulation hors sujet                 | Non            |

**Choix pour la démo** : `qwen3.5:4b` reste le modèle principal : 10/10 choix d’outils dans
la campagne historique, 19/22 au score RAG + persona et 37 tok/s GPU ou 11 tok/s CPU chez
Alban. `gemma4:e4b` reste le plan B : 10/10 outils, 18/22 RAG et 64/16,2 tok/s GPU/CPU.
`nomic-embed-text` reste retenu pour les embeddings, sans comparaison de génération.
Ce choix est un compromis pour notre scénario ; aucun des deux ne réussit les six tâches de
français et les scores RAG ne valident pas toutes les affirmations ou les sources.

Les cases « Non » du tableau historique correspondent aux arbitrages suivants :

- Qwen 2B et Ministral : 9/10 outils, contre 10/10 pour les deux modèles conservés, et
  17/22 ou 18/22 RAG avec des défauts de français documentés.
- Qwen 9B : 18/22 RAG, 9/10 outils et 20/6,4 tok/s GPU/CPU ; davantage de mémoire et
  moins de débit que Qwen 4B sans gain mesuré sur ces critères.
- Llama 3.2 : 6/10 outils ; Granite, Phi et Mistral : 4/10, sans aucun appel d’outil dans
  les cas attendus de la campagne historique. Leur vitesse ou leur taille ne compensent pas
  cette limite pour le scénario qui utilise fichiers et mémoire.
- Bonsai : l’alias historique n’est pas identifié avec certitude. Le candidat officiel PrismML
  Q1_0 ne justifie pas son adoption : cinq sorties de français sur six sont des délibérations
  anglaises coupées. Ses mesures ne remplacent pas celles d’Alban sous l’alias `bonsai2`.
- Les deux modèles ajoutés restent non retenus : `sensai-llama3.2` donne 9/10 outils et
  17/22 RAG ; `gemma3:4b` donne 18/22 RAG mais sans appels d’outils natifs dans Ollama.

Les chiffres d’outils et de débit historiques viennent de la RTX 4060 d’Alban ; les résultats
RAG/français et les mesures complémentaires de VRAM viennent de la RTX 4070. Les dix digests
de cette campagne de qualité correspondent à ceux de la campagne de vitesse RTX 4070, mais
les digests historiques d’Alban ne sont pas connus. Ce bilan ne modifie pas la configuration
active de Sensai et ne remplace pas les 35 cas de validation de la démo encore à jouer.

## Complément : exécution réelle des outils du ticket #83

Le 27/10/2026, les mêmes dix cas sont passés dans le moteur Sensai avec les vrais outils :
fichiers et mémoire temporaires, recherche SearXNG réelle et calcul dans Docker. Température 0,
seed 42, contexte 8192, sortie limitée à 512 tokens par appel, cinq tours maximum.
[Protocole, machine et preuves](../benchmarks.md#ticket-83-live-tool-execution-on-the-six-requested-models).

| Modèle          | Actions demandées réussies | Questions simples sans outil | Limite de la réponse après exécution                                                               |
| --------------- | -------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------- |
| qwen3.5:4b      | 6/6                        | 4/4                          | Recherche exécutée, mais ajout erroné sur les DEEE ; lecture résumée                               |
| llama3.2        | 6/6                        | 0/4                          | Inverse une consigne du fichier ; ajoute des catégories de déchets sans fondement                  |
| sensai-llama3.2 | 3/6                        | 4/4                          | Appel supplémentaire erroné après listing ; mémoire absente ; résultat Python inventé après erreur |
| mistral:7b      | 0/6                        | 4/4                          | Décrit des appels sans les exécuter ; invente fichier et résultat numérique                        |
| phi4-mini       | 0/6                        | 4/4                          | Affiche du pseudo-code au lieu d'appels natifs                                                     |
| gemma3:4b       | Non pris en charge         | n/a                          | Requête réelle avec outils refusée par Ollama, HTTP 400                                            |

Les colonnes chiffrées vérifient l'effet de l'outil et l'absence d'appels inutiles, pas la
justesse globale du texte. Une réponse directe peut donc réussir le contrôle « sans outil »
et rester fausse. Pour `sensai-llama3.2`, le listing est bien exécuté, mais l'appel suivant lit
un mauvais chemin et conduit à une fausse réponse : le cas complet échoue.

Cette validation confirme le choix de Qwen pour les opérations attendues, tout en montrant
une limite persistante : **le modèle peut inventer après un résultat d'outil correct**.
Les scores historiques de choix d'outils restent séparés de ces nouveaux essais d'exécution.
Les six modèles du ticket sont désormais évalués sur cette dimension ; cela ne signifie pas
qu'ils réussissent tous, et les 35 cas de démo ne sont pas encore joués.
