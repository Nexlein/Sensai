# Où trouver quoi pendant la défense

À garder ouvert dans un onglet. Chaque question probable du jury pointe vers le doc à lire et le code
à montrer. Les numéros de ligne correspondent à `main` au 1er novembre.

Pour ouvrir vite :

- **GitHub** : sur la page du dépôt, la touche `t` ouvre la recherche de fichier ; un lien `#L15`
  surligne la ligne.
- **Éditeur** : le sélecteur de fichiers (`Ctrl+P` dans Zed et VS Code) accepte `chemin:ligne`, par
  exemple `injection.py:15`.

## Architecture

| Question du jury                            | Doc                                                                   | Code                                                                                                                                                                                      |
| ------------------------------------------- | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Comment se passe un tour, de bout en bout ? | [architecture.md](../architecture.md#one-turn)                        | [`core/engine.py:111`](../../src/sensai/core/engine.py#L111) `ChatEngine.send`                                                                                                            |
| Pas de framework ? Appels HTTP directs ?    | [architecture.md](../architecture.md#design-choices-in-one-line-each) | [`providers/ollama.py:114`](../../src/sensai/providers/ollama.py#L114) `/api/chat`, [`:178`](../../src/sensai/providers/ollama.py#L178) `/api/embed`                                      |
| Comment on coupe une feature ?              | [configuration.md](../configuration.md#every-setting)                 | [`core/config.py:52`](../../src/sensai/core/config.py#L52) `ToolsConfig`, puis une section `enabled` par feature ; [`:69`](../../src/sensai/core/config.py#L69) `fs_allowed_root = false` |
| Les erreurs ne remontent jamais ?           | [securite-rgpd.md](securite-rgpd.md#gestion-des-erreurs)              | [`interfaces/web/routes.py:142`](../../src/sensai/interfaces/web/routes.py#L142) les trois `except` du tour web                                                                           |

## Contexte et prompt

| Question du jury                    | Doc                                                                    | Code                                                                                                                                                 |
| ----------------------------------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pourquoi cet ordre dans le prompt ? | [observabilite.md](observabilite.md#pourquoi-cet-ordre)                | [`core/prompt.py:72`](../../src/sensai/core/prompt.py#L72) persona, confidentialité, mémoire, RAG, historique                                        |
| Montrez le prompt exact             | [observabilite.md](observabilite.md#logs-du-prompt-complet)            | `/prompt` en direct ; [`eval/logger.py:88`](../../src/sensai/eval/logger.py#L88) `logs/prompts.jsonl`                                                |
| Pourquoi cette fiche d'assistant ?  | [scenario-tek1.md](scenario-tek1.md#pré-prompt--pourquoi-chaque-règle) | [`demo/tek1/persona.md`](../../demo/tek1/persona.md)                                                                                                 |
| Et quand le contexte est plein ?    | [limites.md](limites.md#la-fenêtre-de-contexte)                        | [`core/budget/manager.py:32`](../../src/sensai/core/budget/manager.py#L32) M2, [`tokens.py:9`](../../src/sensai/core/budget/tokens.py#L9) estimation |

## Modèles et paramètres

| Question du jury                       | Doc                                                      | Code                                                                                             |
| -------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Paramètres, quantification, cache KV   | [modeles.md](modeles.md#paramètres-et-empreinte-mémoire) | —                                                                                                |
| Pourquoi Qwen ? Les autres familles ?  | [modeles.md](modeles.md#familles-de-modèles)             | —                                                                                                |
| Génératif ou embedding ?               | [modeles.md](modeles.md#génératif-vs-embedding)          | [`providers/ollama.py:162`](../../src/sensai/providers/ollama.py#L162) `OllamaEmbeddingProvider` |
| Pourquoi température 0 ? Quel impact ? | [benchmarks.md](benchmarks.md#ab-4--température)         | [`sensai.example.toml`](../../sensai.example.toml) `[options]`                                   |
| Pourquoi la réflexion est coupée ?     | [../benchmarks.md](../benchmarks.md#thinking-effort)     | [`core/streaming.py:92`](../../src/sensai/core/streaming.py#L92) `think: false`                  |
| Vos benchmarks de ressources ?         | [../benchmarks.md](../benchmarks.md#in-short)            | `/ps` en direct ; [`providers/ollama.py:34`](../../src/sensai/providers/ollama.py#L34) `/api/ps` |

## Évaluation

| Question du jury               | Doc                                                                            | Code ou commande                                                                                       |
| ------------------------------ | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Amélioration mesurée ?         | [benchmarks.md](benchmarks.md#ab-1--rag-activé-vs-désactivé-mesure-principale) | [`eval/bench/rag.py:103`](../../src/sensai/eval/bench/rag.py#L103) les 3 conditions                    |
| Comment la note est calculée ? | [benchmarks.md](benchmarks.md#ab-1--rag-activé-vs-désactivé-mesure-principale) | [`eval/bench/rag.py:82`](../../src/sensai/eval/bench/rag.py#L82) `is_correct`, mots-clés               |
| Vérification autonome ?        | [tests.md](tests.md)                                                           | `uv run python -m sensai.eval.adversarial` (1 s) ; `uv run pytest -q tests/eval/guardrails` (10 s)     |
| Vos limites ?                  | [limites.md](limites.md#à-dire-en-30-secondes)                                 | [`eval/adversarial/corpus.py:48`](../../src/sensai/eval/adversarial/corpus.py#L48) les cas `known_gap` |

## Sécurité

| Question du jury                         | Doc                                                                       | Code                                                                                                                                                                                                         |
| ---------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Où bloquez-vous les injections ?         | [securite-rgpd.md](securite-rgpd.md#injections-de-prompt)                 | [`eval/guardrails/injection.py:15`](../../src/sensai/eval/guardrails/injection.py#L15) les règles                                                                                                            |
| Où masquez-vous les données perso ?      | [securite-rgpd.md](securite-rgpd.md#fuites-de-données)                    | [`pii_rules.py:22`](../../src/sensai/eval/guardrails/pii_rules.py#L22) les règles, [`checksums.py:6`](../../src/sensai/eval/guardrails/checksums.py#L6) Luhn, IBAN, n° de sécu                               |
| À quels moments les garde-fous passent ? | [securite-rgpd.md](securite-rgpd.md#où-le-code-se-protège)                | Entrée [`engine.py:133`](../../src/sensai/core/engine.py#L133), outils [`tool_runner.py:74`](../../src/sensai/core/tool_runner.py#L74), sortie [`streaming.py:208`](../../src/sensai/core/streaming.py#L208) |
| Il peut écrire n'importe où ?            | [securite-rgpd.md](securite-rgpd.md#actions-dangereuses)                  | [`tools/base.py:34`](../../src/sensai/tools/base.py#L34) `Path traversal rejected`                                                                                                                           |
| Où est la confirmation ?                 | [securite-rgpd.md](securite-rgpd.md#actions-dangereuses)                  | [`tools/fs.py:88`](../../src/sensai/tools/fs.py#L88) `WriteFileTool` sensible, [`core/tool_runner.py:57`](../../src/sensai/core/tool_runner.py#L57) le contrôle                                              |
| RGPD ?                                   | [securite-rgpd.md](securite-rgpd.md#données-traitées-scénario-tek-1-démo) | —                                                                                                                                                                                                            |

## Cas d'usage et décisions

| Question du jury                             | Doc                                                                                                                                                                                    |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Votre scénario, votre utilisateur ?          | [scenario-tek1.md](scenario-tek1.md)                                                                                                                                                   |
| Quelle story pour cette feature ?            | [scenario-tek1.md](scenario-tek1.md#traçabilité--moment-de-la-démo-besoin-feature-user-stories), [stories Tek 1](../USER_STORIES.md#scenario-tek-1-student-in-the-c-pool-defense-demo) |
| Les stories avant le code ?                  | [retours-midterm.md](retours-midterm.md#cas-dusage)                                                                                                                                    |
| Ce qui a changé en route ?                   | [decisions.md](decisions.md#pivots--features-modifiées-ou-retirées-en-cours-de-route)                                                                                                  |
| Pourquoi ce choix, et pas un autre ?         | [decisions.md](decisions.md#décisions-majeures-et-arbitrages)                                                                                                                          |
| Si c'était à refaire ?                       | [decisions.md](decisions.md#alternatives--si-cétait-à-refaire)                                                                                                                         |
| Pourquoi pas Copilot ? Combien ça coûte ?    | [couts-benefices.md](couts-benefices.md#comparaison-avec-les-assistants-en-ligne)                                                                                                      |
| Et les features que vous ne montrez pas ?    | [scenario-tek1.md](scenario-tek1.md#features-coupées-pour-ce-scénario)                                                                                                                 |
| Qu'avez-vous corrigé depuis la mi-parcours ? | [retours-midterm.md](retours-midterm.md)                                                                                                                                               |
