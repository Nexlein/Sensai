# Tests

Remarque du jury : « les tests doivent afficher plus que OK », et au moins un test doit tourner
« en vrai », contre un vrai modèle.

## Afficher ce qui est testé

```bash
# nom de chaque test et son résultat
uv run pytest -v

# résumé de tous les tests, y compris ceux qui passent et ceux sautés (avec la raison)
uv run pytest -rA

# couverture par fichier, lignes non couvertes
uv run pytest --cov=sensai --cov-report=term-missing

# un seul domaine, par exemple les guardrails
uv run pytest tests/eval/guardrails -v
```

Les noms de tests sont des phrases (`test_send_rejects_empty_input_before_provider_call`,
`test_cancelling_a_turn_drops_the_unanswered_user_message`) : avec `-v`, la
sortie se lit comme une liste de comportements garantis. Pour la soutenance, montrer la sortie `-v`
d'un dossier, puis la couverture globale.

Raccourcis du `Makefile` :

```bash
make test-verbose   # uv run pytest -v -rs : chaque test, et la raison des tests sautés
make coverage       # couverture de branches, lignes manquantes, rapport HTML dans htmlcov/
make test-live      # uniquement les tests marqués `live` (vrai modèle, Docker), transcripts inclus
```

La couverture est mesurée par branche (`[tool.coverage]` dans `pyproject.toml`) et la CI échoue
sous 96 %. Le job de test publie le tableau de couverture dans le résumé de l'exécution GitHub.

### Couverture par feature

Mesurée le 2026-10-26 (`make coverage`, couverture de branches).

| Feature                 | Dossier de tests          | Nb tests | Couverture |
| ----------------------- | ------------------------- | -------- | ---------- |
| Moteur, boucle d'outils | `tests/core/`             | 315      | 98 %       |
| Budget (M2)             | `tests/core/budget/`      | 46       | 100 %      |
| Guardrails (EV2)        | `tests/eval/guardrails/`  | 276      | 99 %       |
| Adversarial (EV4)       | `tests/eval/adversarial/` | 18       | 95 %       |
| Juge (EV1)              | `tests/eval/judge/`       | 33       | 98 %       |
| RAG (R1)                | `tests/memory/rag/`       | 20       | 99 %       |
| Mémoire, sessions       | `tests/memory/`           | 18       | 99 %       |
| Outils (T1-T4)          | `tests/tools/`            | 155      | 98 %       |
| Providers               | `tests/providers/`        | 88       | 98 %       |
| Interfaces              | `tests/interfaces/`       | 184      | 98 %       |
| Parcours complets       | `tests/functional/`       | 33       | (tout)     |
| Comportement du modèle  | `tests/live/`             | 46       | (sautés)   |

Total : 1225 tests passent, 61 sont sautés sans modèle ni Docker, 98 % de couverture.

## Les familles de tests

**Unitaires** (`tests/<module>/`, miroir de `src/sensai/`) : une classe ou une fonction, avec des
faux voisins. Ils couvrent aussi les chemins d'erreur : fichier illisible, base SQLite verrouillée,
serveur MCP qui écrit autre chose que du JSON, embeddings de tailles différentes.

**Contrat** (`tests/tools/test_tool_registry.py`, `tests/providers/test_registry.py`) : chaque outil
intégré a un nom accepté par l'API, une description, un schéma JSON valide dont chaque argument est
documenté, et sa méthode `execute` accepte exactement ce que le schéma annonce. La liste des outils
qui demandent une confirmation est figée dans le test (A3) : en ajouter un exige de modifier le
test. Chaque provider respecte la signature de `LLMProvider`.

**Fonctionnels** (`tests/functional/`) : une vraie session construite par `build_session` (config,
outils, mémoire, guardrails, persistance), seul le modèle est remplacé par `ScriptedLLMProvider`, qui
rejoue des tours écrits à l'avance et garde ce qu'il a reçu. Chaque entrée passe par `process_input`,
comme dans la CLI, la TUI et le web. Exemples : lecture puis réponse, écriture acceptée ou refusée,
recherche web, fait mémorisé retrouvé après `/new`, numéro de téléphone masqué avant le modèle,
injection bloquée sans appel au modèle, plafond de 5 étapes, RAG, session reprise après redémarrage.
`test_cli_process.py` lance le vrai exécutable `sensai` dans un sous-processus.

**Golden files** (`tests/functional/test_prompt_golden.py`) : le prompt système et les définitions
d'outils envoyés au modèle sont comparés à des fichiers de `tests/functional/golden/`. Un changement
de prompt devient un diff relu en revue. Après un changement voulu :
`SENSAI_UPDATE_GOLDEN=1 uv run pytest tests/functional/test_prompt_golden.py`, puis commiter les
fichiers.

**Propriétés** ([Hypothesis](https://hypothesis.readthedocs.io/)) : au lieu de quelques exemples,
des centaines d'entrées générées. Luhn, IBAN et NIR détectent toute faute de frappe sur un chiffre ;
le masquage des PII en streaming donne le même résultat quelle que soit la découpe du flux ; le
découpage RAG reconstitue le texte sans perte ; un chemin validé ne sort jamais de la racine
autorisée, quels que soient les `..`, liens symboliques et `/` combinés.

**Sécurité** : corpus de chemins hostiles pour les outils fichiers (traversée, chemin absolu, lien
symbolique sortant, octet nul, nom de 5000 caractères), en plus de l'évaluation adversariale (EV4).

## Tests « en vrai »

Sautés par défaut, marqués `live`, activés par variable d'environnement. `make test-live` les
sélectionne tous ; chacun affiche sa conversation (question, outils appelés avec leurs arguments,
réponse), visible même quand il passe.

| Test                        | Commande                                                                                      | Prérequis                               |
| --------------------------- | --------------------------------------------------------------------------------------------- | --------------------------------------- |
| Comportement du modèle      | `SENSAI_OLLAMA_TEST_MODEL=qwen3.5:4b make test-live`                                          | Ollama + modèle (+ `nomic-embed-text`)  |
| Choix d'outils (historique) | `SENSAI_OLLAMA_TEST_MODEL=qwen3.5:4b uv run pytest tests/providers/test_ollama.py -k live -v` | Ollama + modèle                         |
| Juge LLM                    | `SENSAI_LIVE_JUDGE=1 uv run pytest tests/eval/judge/test_judge.py -v`                         | Ollama                                  |
| Sandbox Docker              | `SENSAI_LIVE_SANDBOX=1 uv run pytest tests/tools/test_sandbox.py -v`                          | Docker + `python:3.12-alpine`           |
| Serveur MCP GitHub          | `SENSAI_LIVE_MCP=1 uv run pytest tests/tools/test_mcp_live.py -v`                             | Docker + `GITHUB_PERSONAL_ACCESS_TOKEN` |

`tests/live/` vérifie, pour chaque outil, le choix du modèle **et** sa réponse finale :

| Fichier                    | Ce qui est vérifié                                                                                                                                                                |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_live_tool_choice.py` | 14 demandes types : salutation et culture générale sans outil, actualité et météo par `web_search`, fichiers, `run_python`, mémoire                                               |
| `test_live_web.py`         | Fait récent : recherche lancée, réponse tirée des résultats (fait inventé que le modèle ne peut pas connaître), source citée, rien d'inventé si la recherche est vide ou en panne |
| `test_live_compute.py`     | Résultat exact de grands calculs (`4817 × 2309 = 11122453`), petits calculs, script corrigé et relancé après une erreur                                                           |
| `test_live_files.py`       | Réponse tirée du fichier lu, comptage d'un listing, fichier absent signalé, écriture conforme ou refusée                                                                          |
| `test_live_memory.py`      | Fait mémorisé puis réutilisé après `/new`, `recall_memory` quand l'injection automatique est coupée                                                                               |
| `test_live_rag.py`         | Réponses du corpus `data/collecte` (bac jaune secteur B = mercredi), fausse prémisse corrigée (25 km/h)                                                                           |
| `test_live_answers.py`     | Langue de la réponse, pas de code interne inventé, réponses ouvertes notées ≥ 4 par le juge (EV1)                                                                                 |

Options : `SENSAI_OLLAMA_BASE_URL` (défaut `http://localhost:11434`), `SENSAI_LIVE_SANDBOX=1` pour
exécuter `run_python` dans Docker au lieu d'un bouchon, `SENSAI_LIVE_SEARXNG=1` pour le test contre le
SearXNG de `compose.yaml`. Les réglages d'échantillonnage sont fixés (`temperature = 0`, `seed = 42`),
mais un petit modèle peut encore varier : un échec décrit une limite du modèle ou du prompt, pas un
bug du code. Lire la conversation affichée avant de conclure.

**Pour la soutenance** : jouer `make test-live` en direct, ou au moins `test_live_web.py` et
`test_live_compute.py`. Ils prouvent que le modèle choisi appelle les bons outils et répond juste,
pas seulement que le code fonctionne avec un faux provider.

Le benchmark A/B ([benchmarks.md](benchmarks.md)) est l'autre test « en vrai » : il mesure la qualité
des réponses, là où les tests unitaires vérifient le comportement du code.

## Différence à expliquer au jury

| Type              | Provider              | Vérifie                                    | Déterministe                        |
| ----------------- | --------------------- | ------------------------------------------ | ----------------------------------- |
| Unitaire          | `MockLLMProvider`     | Notre code : pipeline, guardrails, erreurs | Oui                                 |
| Fonctionnel       | `ScriptedLLMProvider` | Les parcours complets d'une session        | Oui                                 |
| Propriétés        | Aucun                 | Des invariants, sur des entrées générées   | Non, mais un échec est rejouable    |
| Live              | Ollama réel           | Que le modèle choisi suit nos outils       | Non                                 |
| Adversarial (EV4) | Faux provider         | Que les attaques sont bloquées             | Oui                                 |
| Benchmark / juge  | Ollama réel           | Qualité des réponses, mesurée              | Presque (`seed`, `temperature = 0`) |
