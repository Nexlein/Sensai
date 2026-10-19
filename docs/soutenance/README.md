# Préparation soutenance

Dossier de préparation du keynote et des questions du jury. Chaque ligne du tableau ci-dessous
reprend une exigence annoncée, l'état réel du projet et le document qui y répond.

Légende : ✅ fait · ⚠️ partiel · ❌ à faire

## Documents

| Document                                 | Répond à                                                               |
| ---------------------------------------- | ---------------------------------------------------------------------- |
| [scenario.md](scenario.md)               | Utilisateur cible, besoin métier, cohérence latence, pré-prompt        |
| [demo-script.md](demo-script.md)         | Scène de théâtre, script minuté, plan de repli                         |
| [configuration.md](configuration.md)     | Fichier de config, activation des features, température, contexte      |
| [observabilite.md](observabilite.md)     | Logs du prompt complet, compteur de tokens, tokens/s, RAM/VRAM         |
| [modeles.md](modeles.md)                 | Culture IA (critère 7), choix du modèle, tableau des modèles           |
| [benchmarks.md](benchmarks.md)           | Évaluation A/B (critère 9), métriques, rejouabilité                    |
| [prompts-de-test.md](prompts-de-test.md) | Prompts de test, limites du modèle, hallucinations                     |
| [tests.md](tests.md)                     | Tests unitaires lisibles, tests « en vrai » contre Ollama              |
| [securite-rgpd.md](securite-rgpd.md)     | RGPD, scénario de fuite, où le code bloque injections et fuites        |
| [couts-benefices.md](couts-benefices.md) | Analyse coûts-bénéfices (régie de collecte et équipe)                  |
| [decisions.md](decisions.md)             | Critère 16 : choix, exclusions, alternatives, « si c'était à refaire » |

Le jeu de données du scénario est dans [`data/collecte/`](../../data/collecte/) (documents fictifs).
Les user stories restent dans [`../USER_STORIES.md`](../USER_STORIES.md).

## Prérequis éliminatoires

| Exigence                                           | État | Où / ce qui manque                                                                                                                      |
| -------------------------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Lancer l'app et envoyer un prompt                  | ✅   | `uv run sensai chat` (CLI), `--ui tui`, `--ui web`                                                                                      |
| Config pour activer/désactiver les features        | ⚠️   | `sensai.toml` couvre guardrails, mémoire, raisonnement, fs, MCP, eval. RAG seulement par `--rag-dir`, pas de bascule web search/sandbox |
| Modifier température et taille du contexte         | ❌   | Aucun `options` envoyé à Ollama. Spécification : [configuration.md](configuration.md#température-et-contexte-à-implémenter)             |
| Adapter la config au modèle                        | ⚠️   | `budget.max_tokens` (8192) indépendant du `num_ctx` réel d'Ollama : voir [configuration.md](configuration.md#profils-par-modèle)        |
| Aucune erreur visible (exceptions interceptées)    | ✅   | `ProviderError`, `ConfigError`, erreurs d'outils en texte. Voir [securite-rgpd.md](securite-rgpd.md#gestion-des-erreurs)                |
| Afficher le prompt complet reconstitué (logs)      | ❌   | `TurnLogger` existe mais n'est pas branché. Spécification : [observabilite.md](observabilite.md#logs-du-prompt-complet)                 |
| Compteur de tokens                                 | ⚠️   | Estimation 4 caractères/token affichée en direct. Les vrais comptes d'Ollama (`prompt_eval_count`, `eval_count`) sont ignorés           |
| Meilleur pré-prompt / IA spécialisée               | ⚠️   | `TOOL_USE_GUIDANCE` générique, `Persona` non branché. Proposition : [scenario.md](scenario.md#pré-prompt-proposé)                       |
| Exemples dans le README partout                    | ⚠️   | Exemples présents par feature ; ajouter ceux de cette doc une fois les features faites                                                  |
| Débit (tokens/s) : le voir, le savoir, l'expliquer | ❌   | [observabilite.md](observabilite.md#débit-tokenss)                                                                                      |
| Consommation RAM / VRAM                            | ✅   | `/ps` (taille, CPU/GPU, contexte). Voir [observabilite.md](observabilite.md#ram-et-vram)                                                |
| Prompts de test                                    | ⚠️   | [prompts-de-test.md](prompts-de-test.md), à jouer et remplir                                                                            |
| Tableau des modèles + benchmarks                   | ❌   | Gabarit dans [modeles.md](modeles.md#tableau-des-modèles-testés), mesures à faire sur nos machines                                      |

## Critères notés

| Critère                                     | État | Document                                                                             |
| ------------------------------------------- | ---- | ------------------------------------------------------------------------------------ |
| 7. Culture IA (4 pts)                       | ⚠️   | [modeles.md](modeles.md), à répéter à l'oral                                         |
| 9. Amélioration mesurée (3 pts)             | ⚠️   | [benchmarks.md](benchmarks.md) ; le script A/B RAG reste à écrire                    |
| Tests qui affichent plus que « OK »         | ⚠️   | [tests.md](tests.md)                                                                 |
| Limites du modèle (hallucination, codename) | ⚠️   | [prompts-de-test.md](prompts-de-test.md#limites-du-modèle)                           |
| Scénario, persona, latence                  | ⚠️   | [scenario.md](scenario.md) : scénario fixé, à valider par l'équipe                   |
| Jeu de données cohérent                     | ⚠️   | [`data/collecte/`](../../data/collecte/) : base à enrichir                           |
| 2 user stories par feature                  | ✅   | [`../USER_STORIES.md`](../USER_STORIES.md) ; s'entraîner au quiz « story → feature » |
| Démo théâtralisée                           | ⚠️   | [demo-script.md](demo-script.md), à répéter                                          |
| RGPD + fuite + contraintes techniques       | ⚠️   | [securite-rgpd.md](securite-rgpd.md)                                                 |
| Coûts-bénéfices                             | ⚠️   | [couts-benefices.md](couts-benefices.md) : hypothèses à confirmer                    |
| Sécurité montrée dans le code               | ✅   | [securite-rgpd.md](securite-rgpd.md#où-le-code-se-protège)                           |
| 16. Décisions et alternatives (6 pts)       | ⚠️   | [decisions.md](decisions.md)                                                         |

## Priorités de développement avant la soutenance

Dans l'ordre, ce qui bloque un prérequis éliminatoire :

1. `[model]` dans `sensai.toml` : `temperature`, `num_ctx`, `top_p`, `seed`, envoyés dans `options` d'`/api/chat`. Aligner `budget.max_tokens` sur `num_ctx`.
2. `[rag]` dans `sensai.toml` (`enabled`, `dir`, `model`, `db`, `top_k`, `chunk_size`) et bascules `tools.web_search`, `tools.sandbox`.
3. Log du prompt complet envoyé à Ollama (`logs/prompts.jsonl` + `/prompt` pour afficher le dernier).
4. Lire `prompt_eval_count`, `eval_count`, `eval_duration` du dernier message d'Ollama : vrai compteur de tokens et tokens/s affichés après chaque réponse.
5. Persona « collecte » branchée (`Persona` existe déjà dans `domain/models.py`).
6. Script A/B RAG (`python -m sensai.eval.bench`), voir [benchmarks.md](benchmarks.md#script-à-écrire).

Chaque feature ajoutée apporte ses deux user stories dans `docs/USER_STORIES.md`.
