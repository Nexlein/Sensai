# Benchmarks : amélioration mesurée

Critère 9 (3 pts) : une comparaison A/B nette avec une baseline, une métrique explicite, et un
script rejouable en direct qui retrouve les mêmes ordres de grandeur.

## Ce qui existe déjà

| Outil              | Commande                                           | Métrique                                      | Ollama |
| ------------------ | -------------------------------------------------- | --------------------------------------------- | ------ |
| Suite adversariale | `uv run python -m sensai.eval.adversarial`         | Taux de détection, taux de faux positifs      | Non    |
| Juge LLM (EV1)     | `uv run python -m sensai.eval.judge replies.jsonl` | Pertinence et cohérence (1-5), fidélité (0-1) | Oui    |

La suite adversariale est déjà un A/B : guardrails activés vs `enabled = false` (tout passe, la suite
échoue). Rejouable en 2 s, sans réseau ni modèle : **le filet de sécurité de la démo**.

```bash
uv run python -m sensai.eval.adversarial
```

## A/B 1 : RAG activé vs désactivé (mesure principale)

**Hypothèse** : sur des questions dont la réponse n'existe que dans `data/collecte/`, le RAG fait
passer l'exactitude de ~0 % (le modèle invente) à plus de 70 %, pour un surcoût de latence mesurable.

**Protocole** :

- Même modèle, `temperature = 0`, `seed = 42`, même machine, modèle préchauffé.
- 20 questions avec réponse de référence (`docs/soutenance/bench-questions.jsonl`, à créer depuis le
  tableau ci-dessous), dont 4 sans réponse dans le corpus (le bon comportement est de le dire).
- Condition A : sans `--rag-dir`. Condition B : avec `--rag-dir data/collecte`.

**Métriques** :

| Métrique             | Calcul                                                                                       |
| -------------------- | -------------------------------------------------------------------------------------------- |
| Exactitude factuelle | Part des réponses contenant tous les mots-clés attendus (insensible à la casse/accents)      |
| Refus correct        | Part des questions hors corpus où le modèle dit ne pas savoir                                |
| Fidélité (juge EV1)  | Part des affirmations `supported` par le contexte (condition B uniquement)                   |
| Latence              | Temps total moyen et temps avant le premier token (`total_duration`, `prompt_eval_duration`) |
| Tokens de prompt     | `prompt_eval_count` moyen : le coût du contexte ajouté                                       |

**Questions** (extrait, faits inventés présents seulement dans le corpus) :

| #   | Question                                                                 | Mots-clés attendus   | Source                    |
| --- | ------------------------------------------------------------------------ | -------------------- | ------------------------- |
| 1   | Quel jour est collecté le bac jaune dans le secteur B ?                  | `mercredi`           | calendrier-secteurs.md    |
| 2   | À quelle heure commence la collecte dans le secteur A ?                  | `5 h 30`             | calendrier-secteurs.md    |
| 3   | C'est quoi l'Opération Hérisson ?                                        | `neige`, `verglas`   | plan-hivernal-herisson.md |
| 4   | Pendant l'Opération Hérisson, de combien est décalée la prise de poste ? | `1 h` ou `une heure` | plan-hivernal-herisson.md |
| 5   | Vitesse max quand un ripeur est sur le marchepied ?                      | `25`                 | securite-collecte.md      |
| 6   | Quel est le délai pour déclarer un presqu'accident ?                     | `24 h`               | procedure-incidents.md    |
| 7   | Quelle couleur d'autocollant pour un refus de collecte ?                 | `orange`             | procedure-incidents.md    |
| 8   | Les pots de yaourt vont dans quel bac ?                                  | `jaune`              | consignes-tri.md          |
| 9   | Combien de passages d'encombrants par an par foyer ?                     | `4`                  | consignes-tri.md          |
| 10  | Qui contacter pour un bac volé ?                                         | `service usagers`    | procedure-incidents.md    |
| 17  | Quel est le salaire d'un ripeur à la régie ?                             | (refus attendu)      | hors corpus               |
| 18  | Quel est le code d'accès du portail du dépôt ?                           | (refus attendu)      | hors corpus               |

Compléter jusqu'à 20 en lisant le corpus.

**Résultats** (à remplir, 3 passages, médiane) :

| Condition    | Exactitude | Refus correct | Fidélité (juge) | Latence moy. | 1er token | Tokens prompt moy. |
| ------------ | ---------- | ------------- | --------------- | ------------ | --------- | ------------------ |
| A : sans RAG |            |               | n/a             |              |           |                    |
| B : avec RAG |            |               |                 |              |           |                    |

**Arbitrage à commenter** : le RAG ajoute ~5 chunks × 500 caractères ≈ 600 tokens par question →
temps avant le premier token plus long, contexte consommé plus vite. C'est le compromis
« précision vs latence » attendu au critère 16.

## A/B 2 : pré-prompt générique vs spécialisé

Même jeu de questions, condition B (RAG activé), avec `TOOL_USE_GUIDANCE` seul vs la persona de
[scenario.md](scenario.md#pré-prompt-proposé).

| Condition            | Exactitude | Source citée | Refus correct |
| -------------------- | ---------- | ------------ | ------------- |
| Pré-prompt générique |            |              |               |
| Persona collecte     |            |              |               |

## A/B 3 : compression du budget (M2)

Session longue (30 tours scriptés) avec `budget.max_tokens = 2048` vs compression désactivée.
Métriques : tokens de prompt au tour 30, latence au tour 30, et le modèle se souvient-il d'un fait
donné au tour 2 (oui / non). Montre le compromis « coût de contexte vs perte d'information ».

## A/B 4 : température

Questions 1 à 10, condition B, `temperature` 0.0 vs 0.7 vs 1.2, 5 passages chacune sans `seed`.
Métriques : exactitude moyenne et variance entre passages.

## Script à écrire

`python -m sensai.eval.bench` (dans `eval/bench/`, avec ses tests dans `tests/eval/bench/`) :

```bash
uv run python -m sensai.eval.bench \
  --questions docs/soutenance/bench-questions.jsonl \
  --rag-dir data/collecte --model qwen3.5:4b --runs 3
```

Format d'une ligne de questions :

```json
{"id": 1, "question": "Quel jour est collecté le bac jaune dans le secteur B ?", "expected": ["mercredi"], "source": "calendrier-secteurs.md"}
{"id": 17, "question": "Quel est le salaire d'un ripeur à la régie ?", "expected": [], "unanswerable": true}
```

Sortie attendue :

```text
== RAG A/B · qwen3.5:4b · 20 questions × 3 runs ==
condition   accuracy  refusal  latency   ttft    prompt_tok
no-rag        5%       25%     8.2 s    0.9 s       210
rag          80%       75%    11.6 s    2.8 s       830
delta       +75 pts   +50 pts  +3.4 s   +1.9 s      +620
```

Contraintes : passe par `build_session` (même pipeline que la CLI), `temperature = 0` et `seed` fixés
(dépend de `[options]`, voir [configuration.md](configuration.md)), écrit aussi les réponses au format
du juge pour enchaîner `python -m sensai.eval.judge`. Code de sortie non nul si une condition échoue
complètement (Ollama absent → message une ligne, pas de trace).

## Rejouer en direct

1. Préchauffer le modèle (voir [demo-script.md](demo-script.md#préparation-avant-dentrer-en-salle)).
2. Lancer avec `--runs 1` et 10 questions pour tenir en moins de 3 minutes.
3. Comparer aux résultats du tableau : les **ordres de grandeur** doivent tenir (écart d'exactitude
   de plusieurs dizaines de points), pas les valeurs exactes.
