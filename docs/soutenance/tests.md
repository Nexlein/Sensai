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

À ajouter dans le `Makefile` :

```make
test-verbose:
	uv run pytest -v -rs
coverage:
	uv run pytest --cov=sensai --cov-report=term-missing
```

`pytest-cov` est déjà dans les dépendances de dev.

### Couverture par feature (à remplir)

| Feature                 | Dossier de tests          | Nb tests | Couverture |
| ----------------------- | ------------------------- | -------- | ---------- |
| Moteur, boucle d'outils | `tests/core/`             |          |            |
| Budget (M2)             | `tests/core/budget/`      |          |            |
| Guardrails (EV2)        | `tests/eval/guardrails/`  |          |            |
| Adversarial (EV4)       | `tests/eval/adversarial/` |          |            |
| Juge (EV1)              | `tests/eval/judge/`       |          |            |
| RAG (R1)                | `tests/memory/rag/`       |          |            |
| Mémoire, sessions       | `tests/memory/`           |          |            |
| Outils (T1-T4)          | `tests/tools/`            |          |            |
| Providers               | `tests/providers/`        |          |            |
| Interfaces              | `tests/interfaces/`       |          |            |

## Tests « en vrai »

Sautés par défaut, activés par variable d'environnement :

| Test                     | Commande                                                                                      | Prérequis                               |
| ------------------------ | --------------------------------------------------------------------------------------------- | --------------------------------------- |
| Choix d'outils du modèle | `SENSAI_OLLAMA_TEST_MODEL=qwen3.5:4b uv run pytest tests/providers/test_ollama.py -k live -v` | Ollama + modèle                         |
| Juge LLM                 | `SENSAI_LIVE_JUDGE=1 uv run pytest tests/eval/judge/test_judge.py -v`                         | Ollama                                  |
| Sandbox Docker           | `SENSAI_LIVE_SANDBOX=1 uv run pytest tests/tools/test_sandbox.py -v`                          | Docker + `python:3.12-alpine`           |
| Serveur MCP GitHub       | `SENSAI_LIVE_MCP=1 uv run pytest tests/tools/test_mcp_live.py -v`                             | Docker + `GITHUB_PERSONAL_ACCESS_TOKEN` |

**Pour la soutenance** : jouer en direct le test Ollama (il couvre salutation, lecture de fichier,
recherche web simulée, refus puis nouveau message). Il prouve que le modèle choisi appelle
réellement les bons outils, pas seulement que le code fonctionne avec un faux provider.

Le benchmark A/B ([benchmarks.md](benchmarks.md)) est l'autre test « en vrai » : il mesure la qualité
des réponses, là où les tests unitaires vérifient le comportement du code.

## Différence à expliquer au jury

| Type              | Provider          | Vérifie                                    | Déterministe                        |
| ----------------- | ----------------- | ------------------------------------------ | ----------------------------------- |
| Unitaire          | `MockLLMProvider` | Notre code : pipeline, guardrails, erreurs | Oui                                 |
| Live              | Ollama réel       | Que le modèle choisi suit nos outils       | Non                                 |
| Adversarial (EV4) | Faux provider     | Que les attaques sont bloquées             | Oui                                 |
| Benchmark / juge  | Ollama réel       | Qualité des réponses, mesurée              | Presque (`seed`, `temperature = 0`) |
