# Scénario : Sensai Piscine (démo de la défense)

> Le scénario joué à la défense, depuis le 1er novembre ([demo-script.md](demo-script.md)). Le
> scénario de la régie de collecte ([scenario.md](scenario.md)) reste celui du corpus des benchmarks.
> Le pivot est daté dans [decisions.md](decisions.md#pivots--features-modifiées-ou-retirées-en-cours-de-route).

## Contexte

En première année à Epitech (Tek 1), la piscine C enchaîne un sujet par jour. Chaque soir, une
moulinette compile et corrige le dépôt rendu. Deux règles pèsent sur tout le reste : le code doit
respecter la norme, et copier du code qu'on ne sait pas expliquer, c'est un -42 sur le jour entier.

## Utilisateur : Alban, en Tek 1

Alban joue son propre rôle, deux ans plus tôt. Rien n'est à inventer : il a vécu la piscine.

- Bloqué à 23 h sur un exercice, la veille du rendu.
- Étudiant : pas de budget pour un abonnement.
- Sait se servir d'un terminal et suivre un README : c'est lui qui installe Sensai pendant la pièce.
- PC portable personnel sous Linux, avec une carte graphique (RTX 4060). Sensai marche aussi sans
  carte graphique, plus lentement (mesuré, voir plus bas).
- Reçoit des messages de son binôme avec son numéro et son mail, et trouve du code sur internet.

**Besoins** :

1. **Une réponse tirée de son sujet**, pas d'internet : fonctions autorisées, date limite, norme.
2. **De l'aide qui le fait apprendre** : une fonction à la fois, à la norme, expliquée ligne par
   ligne, pour pouvoir la défendre.
3. **Garder la main sur son dépôt** : rien n'est écrit sans son accord, et jamais hors du dossier.
4. **Ne pas exposer son binôme**, et ne pas se faire piéger par du code trouvé en ligne.
5. **Reprendre le lendemain** là où il s'était arrêté, sans tout réexpliquer.
6. **Ne pas recevoir de règle inventée** : une fausse date limite, c'est un jour à 0.

## Pourquoi un assistant local

| Contrainte                                   | Conséquence                                                               |
| -------------------------------------------- | ------------------------------------------------------------------------- |
| Pas de budget                                | Modèles ouverts sur Ollama, PC déjà acheté : 0 € par mois                 |
| Messages du binôme, code non rendu           | Rien ne sort du PC ; les données personnelles sont masquées en plus       |
| Sujet et norme propres à la piscine          | Le modèle ne les connaît pas : RAG sur `demo/tek1/docs/`                  |
| Travail tard le soir, réseau pas toujours là | Marche hors ligne une fois les modèles téléchargés                        |
| Règle du -42                                 | Fiche d'assistant qui explique au lieu de rendre un jour entier tout fait |

## Cohérence avec la latence locale

Mesuré sur le PC d'Alban le 1er novembre ([temps mesurés](demo-script.md#temps-mesurés)) : 3 à 4 s
avant le premier mot, 5 à 15 s par réponse, environ 1 min 30 d'attente sur toute la démo. Sans carte
graphique, une réponse prend 30 s à 1 min ([../benchmarks.md](../benchmarks.md#in-short)).

- **Acceptable** : une question pendant un exercice, comparée à chercher dans le sujet ou attendre un
  AER. Le streaming affiche le premier mot sans attendre la fin.
- **Non acceptable** : de l'autocomplétion dans l'éditeur, qui doit suivre la frappe. **Exclu du
  scope**.

## Traçabilité : moment de la démo, besoin, feature, user stories

Chaque feature montrée part d'un besoin d'Alban et pointe vers ses user stories
([`../USER_STORIES.md`](../USER_STORIES.md)).

| Moment | Ce qu'Alban fait                                 | Besoin | Feature                    | User stories                                                                                                                                                                                                         |
| ------ | ------------------------------------------------ | ------ | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 4      | Change 4 lignes de `sensai.toml`                 | 1, 2   | Interrupteurs de config    | [Feature Toggles](../USER_STORIES.md#feature-feature-toggles-in-the-config-file) : « enable RAG and tune it in `sensai.toml` », « a ready-made general config file »                                                 |
| 4      | Ouvre la page web, « session piscine » en haut   | 5      | X1 Web UI                  | [Web UI](../USER_STORIES.md#feature-web-ui) : « chat with Sensai in a web page », « approve or refuse each sensitive tool call in the page »                                                                         |
| 5A     | « Quelles fonctions j'ai le droit d'utiliser ? » | 1      | R1 RAG                     | [R1](../USER_STORIES.md#feature-r1-basic-rag) : « ingest my local project documentation », « answers are grounded in my actual documentation »                                                                       |
| 5B     | « Retiens que je m'appelle Alban… », `/memory`   | 5      | M3 Mémoire structurée      | [M3](../USER_STORIES.md#feature-m3-external-structured-memory) : « autonomously record decisions… using tools », « inspect, update, and delete stored memories via `/memory` »                                       |
| 5C     | « Écris la fonction my_strlen »                  | 2      | A5 Persona                 | [Domain Persona](../USER_STORIES.md#feature-domain-persona) : « answer as the Régie's assistant… cite the internal documents », « switch the persona off and on »                                                    |
| 5C     | « Enregistre-la dans CPool_Day04/my_strlen.c »   | 3      | T4 Fichiers                | [T4](../USER_STORIES.md#feature-t4-file-access-within-permissions-filesystem-tools) : « restricted to a project subdirectory », « create or update files in my project »                                             |
| 5C     | Lit l'aperçu, clique `Yes`                       | 3      | A3 Confirmation            | [T4](../USER_STORIES.md#feature-t4-file-access-within-permissions-filesystem-tools) : « approve every file write », [Full Write Preview](../USER_STORIES.md#feature-full-write-preview) : « see every changed line » |
| 5D     | Colle le message du binôme (numéro, mail)        | 4      | EV2 Guardrails (PII)       | [EV2](../USER_STORIES.md#feature-ev2-content--privacy-guardrails) : « personal data I type… masked before it reaches the model », « protected by default »                                                           |
| 5E     | Colle le code GitHub piégé                       | 4      | EV2 Guardrails (injection) | [EV2](../USER_STORIES.md#feature-ev2-content--privacy-guardrails) : « prompt-injection attempts… blocked »                                                                                                           |
| 5F     | `Ctrl+C`, relance avec `--session piscine`       | 5      | M1 Sessions                | [Session Persistence](../USER_STORIES.md#feature-session-persistence) : « resume a named conversation »                                                                                                              |
| 5F     | « À quelle heure ouvre le bâtiment le samedi ? » | 6      | A5 Persona, R1 RAG         | [Domain Persona](../USER_STORIES.md#feature-domain-persona), [R1](../USER_STORIES.md#feature-r1-basic-rag)                                                                                                           |
| 6      | `/persona off`, `/prompt`, `/ps`                 | —      | Observabilité              | [Full Prompt Log](../USER_STORIES.md#feature-full-prompt-log), [Loaded Model Memory](../USER_STORIES.md#feature-loaded-model-memory), [Token Counts](../USER_STORIES.md#feature-real-token-counts-and-throughput)    |

Chaque feature a aussi une story écrite pour Alban, « As a Tek 1 student in the C pool… », avec
le moment de la démo qui la montre : [Scenario: Tek 1 Student](../USER_STORIES.md#scenario-tek-1-student-in-the-c-pool-defense-demo).

**À dire honnêtement** : les stories du tableau ont été écrites avant ce scénario, avec des
utilisateurs génériques (« As a user ») ou ceux des scénarios précédents (réceptionniste, chef
d'équipe de la régie). On ne les a pas réécrites après coup, pour que leur date reste une preuve.
Les stories Tek 1 datent du 1er novembre : elles reformulent les mêmes besoins pour l'étudiant joué.

## Features coupées pour ce scénario

Codées, testées, et coupées dans `sensai.toml` parce qu'Alban n'en a pas besoin :

| Feature           | Pourquoi coupée pour Alban                                                              |
| ----------------- | --------------------------------------------------------------------------------------- |
| T3 Recherche web  | La réponse doit venir de son sujet, pas d'internet                                      |
| T2 Sandbox        | Compiler avec `gcc` lui-même fait partie de l'apprentissage                             |
| A1 Raisonnement   | 50 s de réflexion sur GPU pour une addition, sans meilleure réponse (mesuré)            |
| M2 Compression    | Inutile tant que la conversation tient dans 8 192 tokens (compteur sous chaque réponse) |
| T1 MCP            | Aucun service externe à brancher                                                        |
| EV1 Log pour juge | Sert aux benchmarks, pas à l'étudiant                                                   |

## Jeu de données

Dossier [`demo/tek1/docs/`](../../demo/tek1/docs/), fictif, en Markdown :

| Fichier                | Contenu                                                        | Sert à tester (moment)                             |
| ---------------------- | -------------------------------------------------------------- | -------------------------------------------------- |
| `sujet-jour04.md`      | Rendu, date limite (dimanche 23 h 42), `write` seule autorisée | Faits que le modèle ne peut pas connaître (5A, 5F) |
| `norme-c.md`           | En-tête Epitech, `while` sans `for`, 20 lignes par fonction    | Code à la norme (5C)                               |
| `erreurs-courantes.md` | Segfault, `implicit declaration`, `undefined reference`        | Explication du segfault (5D)                       |
| `entraide.md`          | -42 pour copie, AER, salon `#piscine-aide`                     | Renvoi vers les AER au lieu d'inventer (5F)        |

La date limite à 23 h 42 est inventée exprès : sans RAG, le modèle ne peut pas la trouver.

## Pré-prompt : pourquoi chaque règle

Fiche complète : [`demo/tek1/persona.md`](../../demo/tek1/persona.md), placée en tête de chaque
prompt ([pourquoi cet ordre](observabilite.md#pourquoi-cet-ordre)).

| Règle de la fiche                                      | Besoin servi                              |
| ------------------------------------------------------ | ----------------------------------------- |
| Citer le fichier source entre crochets                 | 1 et 6 : Alban vérifie en un clic         |
| « Je ne trouve pas… » et renvoi vers les AER           | 6 : pas de règle, date ou note inventée   |
| Une fonction à la fois, en-tête, `while`, pas de `for` | 2 : code à la norme de la piscine         |
| Expliquer chaque ligne, jamais un jour entier          | 2 : la règle du -42                       |
| `write_file` pour enregistrer                          | 3 : l'écriture passe par la confirmation  |
| Ne pas deviner `[EMAIL]` et `[PHONE]`                  | 4 : les données masquées restent masquées |

Effet mesuré d'une fiche spécialisée, sur le corpus de la collecte : même exactitude (82 %), mais
la source citée 15 fois sur 18 au lieu de 3 ([benchmarks.md](benchmarks.md#ab-2--pré-prompt-générique-vs-spécialisé)).
