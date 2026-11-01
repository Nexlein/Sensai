# Préparation soutenance

Dossier de préparation de la défense et des questions du jury. Chaque ligne du tableau ci-dessous
reprend une exigence annoncée, l'état réel du projet et le document qui y répond.

Légende : ✅ fait · ⚠️ partiel · ❌ à faire

## Documents

| Document                                 | Répond à                                                                            |
| ---------------------------------------- | ----------------------------------------------------------------------------------- |
| [index-jury.md](index-jury.md)           | Pendant la défense : question du jury → doc à lire et code à montrer                |
| [demo-script.md](demo-script.md)         | Démo « Moi, en Tek 1 » mot pour mot (5 moments + 12 ⭐), plan de repli              |
| [retours-midterm.md](retours-midterm.md) | Chaque point perdu à la mi-parcours : ce qui a changé, la preuve, la phrase à dire  |
| [scenario-tek1.md](scenario-tek1.md)     | Scénario de la démo (Tek 1) : besoins, latence, traçabilité moment → feature → US   |
| [scenario.md](scenario.md)               | Scénario de la régie de collecte, corpus du benchmark RAG                           |
| [persona.md](persona.md)                 | Fiche personnage de Camille Roux (ancienne démo de la régie)                        |
| [configuration.md](configuration.md)     | Fichier de config, activation des features, température, contexte                   |
| [observabilite.md](observabilite.md)     | Logs du prompt complet, compteur de tokens, tokens/s, RAM/VRAM                      |
| [modeles.md](modeles.md)                 | Culture IA (critère 7), choix du modèle, tableau des modèles                        |
| [benchmarks.md](benchmarks.md)           | Évaluation A/B (critère 9), métriques, rejouabilité                                 |
| [prompts-de-test.md](prompts-de-test.md) | Prompts de test, limites du modèle, hallucinations                                  |
| [limites.md](limites.md)                 | Limites du système, chacune avec sa mesure, sa cause et sa parade                   |
| [tests.md](tests.md)                     | Tests unitaires lisibles, tests « en vrai » contre Ollama                           |
| [securite-rgpd.md](securite-rgpd.md)     | RGPD (étudiant et régie), scénario de fuite, où le code bloque injections et fuites |
| [couts-benefices.md](couts-benefices.md) | Analyse coûts-bénéfices (étudiant, régie de collecte, équipe)                       |
| [decisions.md](decisions.md)             | Critère 16 : choix, exclusions, alternatives, « si c'était à refaire »              |

Les deux exemples, documents fictifs et fiche d'assistant, sont dans [`demo/`](../../demo/) :
[`demo/tek1/`](../../demo/tek1/) pour la démo, [`demo/collecte/`](../../demo/collecte/) pour les
benchmarks RAG et persona.
Les user stories restent dans [`../USER_STORIES.md`](../USER_STORIES.md).

## Prérequis éliminatoires

| Exigence                                           | État | Où / ce qui manque                                                                                                                                                                                                      |
| -------------------------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lancer l'app et envoyer un prompt                  | ✅   | `uv run sensai chat` (CLI), `--ui tui`, `--ui web`                                                                                                                                                                      |
| Config pour activer/désactiver les features        | ✅   | `sensai.toml` couvre guardrails, mémoire, raisonnement, fs, MCP, eval, RAG (`[rag]`), web search et sandbox (`[tools]`)                                                                                                 |
| Modifier température et taille du contexte         | ✅   | `[options]` dans `sensai.toml`, `/config set options.temperature`. Voir [configuration.md](configuration.md#température-et-contexte)                                                                                    |
| Adapter la config au modèle                        | ✅   | `num_ctx` = 8192 envoyé par défaut, aligné sur `budget.max_tokens` ; troncature silencieuse prouvée puis corrigée ([../benchmarks.md](../benchmarks.md#context-window-limits))                                          |
| Aucune erreur visible (exceptions interceptées)    | ✅   | `ProviderError`, `ConfigError`, erreurs d'outils en texte. Voir [securite-rgpd.md](securite-rgpd.md#gestion-des-erreurs)                                                                                                |
| Afficher le prompt complet reconstitué (logs)      | ✅   | `/prompt` et `[eval] log_prompts` (`logs/prompts.jsonl`). Voir [observabilite.md](observabilite.md#logs-du-prompt-complet)                                                                                              |
| Compteur de tokens                                 | ✅   | Estimation en direct + vrais comptes Ollama (`prompt_eval_count`, `eval_count`) après chaque réponse, écart loggé                                                                                                       |
| Meilleur pré-prompt / IA spécialisée               | ✅   | `[persona]` + `demo/tek1/persona.md` (démo) ou `demo/collecte/persona.md` (benchmarks), placé en tête du prompt, `/persona on/off`                                                                                      |
| Exemples dans le README partout                    | ✅   | README « What you can try » : un message à taper par feature présentée                                                                                                                                                  |
| Installer depuis la doc seule                      | ✅   | README « Install and run » et [`../INSTALL.fr.md`](../INSTALL.fr.md), joués aux moments 3 et 4 de la démo                                                                                                               |
| Config limitée aux features présentées             | ✅   | [`sensai.example.toml`](../../sensai.example.toml) général ; persona et RAG activés sur scène en 4 lignes                                                                                                               |
| Débit (tokens/s) : le voir, le savoir, l'expliquer | ✅   | Affiché après chaque réponse ; mesuré pour 10 modèles ([modeles.md](modeles.md#tableau-des-modèles-testés)), machines dans [observabilite.md](observabilite.md#débit-tokenss)                                           |
| Consommation RAM / VRAM                            | ✅   | `/ps` (taille, CPU/GPU, contexte). Voir [observabilite.md](observabilite.md#ram-et-vram)                                                                                                                                |
| Prompts de test                                    | ✅   | [prompts-de-test.md](prompts-de-test.md) : 35 résultats consignés (19 conformes, 12 partiels, 4 échecs) ; MCP non configuré, Stop vérifié avant premier texte.                                                          |
| Tableau des modèles + benchmarks                   | ✅   | [modeles.md](modeles.md#bilan-des-douze-modèles) : 12 modèles de dialogue, dont les 6 du ticket ; mesures, RAG/français, sélection et tests live des 6 documentés. Matériels et limites distingués dans les protocoles. |

Pour les deux lignes ci-dessus, ✅ signifie que les mesures et observations sont consignées,
pas que tous les modèles ou tous les cas réussissent. Les essais bornés, l’incompatibilité
d’outils de Gemma 3, l’identité incertaine de l’alias historique Bonsai et les sous-cas non exercés
sont explicités dans les documents liés.
Les campagnes du 27 octobre ont été jouées avant le rebase sur `dev` : elles restent
des observations de cette version, pas une validation de la version rebasée.

## Critères notés

| Critère                               | État | Document                                                                                                             |
| ------------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------- |
| 7. Culture IA (4 pts)                 | ✅   | [modeles.md](modeles.md) : familles (dense ou MoE, licences), à répéter à l'oral                                     |
| 9. Amélioration mesurée (3 pts)       | ✅   | [benchmarks.md](benchmarks.md) : A/B RAG et persona, script rejouable                                                |
| Tests qui affichent plus que « OK »   | ✅   | [tests.md](tests.md) : chaque test par titre, ✓/✗, résumé par zone                                                   |
| Limites du modèle et du système       | ✅   | [limites.md](limites.md), [prompts-de-test.md](prompts-de-test.md#limites-du-modèle)                                 |
| Scénario, persona, latence            | ✅   | [scenario-tek1.md](scenario-tek1.md) (démo), [scenario.md](scenario.md) (benchmarks)                                 |
| Jeu de données cohérent               | ✅   | [`demo/tek1/docs/`](../../demo/tek1/docs/) : sujet, norme, erreurs courantes, entraide                               |
| 2 user stories par feature            | ✅   | [`../USER_STORIES.md`](../USER_STORIES.md) ; s'entraîner au quiz « story → feature »                                 |
| Démo théâtralisée                     | ⚠️   | [demo-script.md](demo-script.md) répété en direct sur le PC d'Alban le 1er novembre ; à rejouer à voix haute         |
| RGPD + fuite + contraintes techniques | ⚠️   | [securite-rgpd.md](securite-rgpd.md)                                                                                 |
| Coûts-bénéfices                       | ⚠️   | [couts-benefices.md](couts-benefices.md) : hypothèses à confirmer                                                    |
| Sécurité montrée dans le code         | ✅   | [securite-rgpd.md](securite-rgpd.md#où-le-code-se-protège)                                                           |
| 16. Décisions et alternatives (6 pts) | ⚠️   | [decisions.md](decisions.md)                                                                                         |
| Ordre du prompt justifié              | ✅   | [observabilite.md](observabilite.md#pourquoi-cet-ordre) : règle par bloc, alternatives écartées                      |
| Pivots et features retirées           | ✅   | [decisions.md](decisions.md#pivots--features-modifiées-ou-retirées-en-cours-de-route) : date, raison, impact, commit |

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

Compléments de [l’issue #83](https://github.com/Nexlein/Sensai/issues/83#issuecomment-6447999487) réalisés le 27 octobre 2026 : les [35 résultats observés](prompts-de-test.md)
sont consignés et le [choix de Qwen](decisions.md#7-modèle-principal--qwen-35-4b) est justifié.
Le périmètre est passé des 6 modèles demandés aux 10 modèles de dialogue déjà comparés par Alban,
puis à 12 après ajout des deux modèles du ticket absents de son tableau (`sensai-llama3.2` et
`gemma3:4b`). `nomic-embed-text`, utilisé pour les embeddings, n’est pas compté parmi ces 12.
Les mesures du premier token et de VRAM sont dans le [complément RTX 4070](../benchmarks.md#first-token-and-vram-rtx-4070-follow-up).
