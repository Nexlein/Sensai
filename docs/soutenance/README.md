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

| Exigence                                           | État | Où / ce qui manque                                                                                                                                                             |
| -------------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Lancer l'app et envoyer un prompt                  | ✅   | `uv run sensai chat` (CLI), `--ui tui`, `--ui web`                                                                                                                             |
| Config pour activer/désactiver les features        | ✅   | `sensai.toml` couvre guardrails, mémoire, raisonnement, fs, MCP, eval, RAG (`[rag]`), web search et sandbox (`[tools]`)                                                        |
| Modifier température et taille du contexte         | ✅   | `[options]` dans `sensai.toml`, `/config set options.temperature`. Voir [configuration.md](configuration.md#température-et-contexte)                                           |
| Adapter la config au modèle                        | ✅   | `num_ctx` = 8192 envoyé par défaut, aligné sur `budget.max_tokens` ; troncature silencieuse prouvée puis corrigée ([../benchmarks.md](../benchmarks.md#context-window-limits)) |
| Aucune erreur visible (exceptions interceptées)    | ✅   | `ProviderError`, `ConfigError`, erreurs d'outils en texte. Voir [securite-rgpd.md](securite-rgpd.md#gestion-des-erreurs)                                                       |
| Afficher le prompt complet reconstitué (logs)      | ✅   | `/prompt` et `[eval] log_prompts` (`logs/prompts.jsonl`). Voir [observabilite.md](observabilite.md#logs-du-prompt-complet)                                                     |
| Compteur de tokens                                 | ✅   | Estimation en direct + vrais comptes Ollama (`prompt_eval_count`, `eval_count`) après chaque réponse, écart loggé                                                              |
| Meilleur pré-prompt / IA spécialisée               | ✅   | `[persona]` + `personas/collecte.md`, placé en tête du prompt, `/persona on/off`. Voir [scenario.md](scenario.md#pré-prompt-proposé)                                           |
| Exemples dans le README partout                    | ⚠️   | Exemples présents par feature ; ajouter ceux de cette doc une fois les features faites                                                                                         |
| Débit (tokens/s) : le voir, le savoir, l'expliquer | ✅   | Affiché après chaque réponse ; mesuré pour 10 modèles ([modeles.md](modeles.md#tableau-des-modèles-testés)), machines dans [observabilite.md](observabilite.md#débit-tokenss)  |
| Consommation RAM / VRAM                            | ✅   | `/ps` (taille, CPU/GPU, contexte). Voir [observabilite.md](observabilite.md#ram-et-vram)                                                                                       |
| Prompts de test                                    | ❌   | [prompts-de-test.md](prompts-de-test.md) : aucun résultat observé consigné                                                                                                     |
| Tableau des modèles + benchmarks                   | ⚠️   | [modeles.md](modeles.md#tableau-des-modèles-testés) : tableau rempli ; périmètre différent de la liste initiale de l'issue #83                                                 |

## Critères notés

| Critère                                     | État | Document                                                                             |
| ------------------------------------------- | ---- | ------------------------------------------------------------------------------------ |
| 7. Culture IA (4 pts)                       | ⚠️   | [modeles.md](modeles.md), à répéter à l'oral                                         |
| 9. Amélioration mesurée (3 pts)             | ✅   | [benchmarks.md](benchmarks.md) : A/B RAG et persona, script rejouable                |
| Tests qui affichent plus que « OK »         | ✅   | [tests.md](tests.md) : chaque test par titre, ✓/✗, résumé par zone                   |
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

1. ~~`[options]` dans `sensai.toml` : `temperature`, `num_ctx`, `top_p`, `seed`, envoyés dans `options` d'`/api/chat`. Aligner `budget.max_tokens` sur `num_ctx`.~~ Fait (#75).
2. ~~`[rag]` dans `sensai.toml` (`enabled`, `dir`, `model`, `db`, `top_k`, `chunk_size`) et bascules `tools.web_search`, `tools.sandbox`.~~ Fait (#76).
3. ~~Log du prompt complet envoyé à Ollama (`logs/prompts.jsonl` + `/prompt` pour afficher le dernier).~~ Fait (#77).
4. ~~Lire `prompt_eval_count`, `eval_count`, `eval_duration` du dernier message d'Ollama : vrai compteur de tokens et tokens/s affichés après chaque réponse.~~ Fait (#78).
5. ~~Persona « collecte » branchée (`Persona` existe déjà dans `domain/models.py`).~~ Fait (#79).
6. ~~Script A/B RAG (`python -m sensai.eval.bench`).~~ Fait, voir [benchmarks.md](benchmarks.md).
7. Réflexion désactivée par défaut : `/effort low` coûte 50 s sur GPU et ~7 min sur CPU pour une addition avec qwen3.5:4b, contre 3 s / 16 s sans (voir [../code-review.md](../code-review.md)).

Chaque feature ajoutée apporte ses deux user stories dans `docs/USER_STORIES.md`.

Pour terminer l’issue #83 : jouer et consigner les prompts de test, justifier le modèle retenu
et expliciter l’évolution de la liste des modèles. Les mesures du premier token et de VRAM du
27 octobre sont dans le [complément RTX 4070](../benchmarks.md#first-token-and-vram-rtx-4070-follow-up).
