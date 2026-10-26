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
passer l'exactitude de ~0 % (le modèle ne sait pas) à plus de 70 %, pour un surcoût de latence
mesurable.

**Protocole** : qwen3.5:4b, `temperature = 0`, `seed = 42`, réflexion désactivée, 22 questions
([`data/bench/rag-questions.jsonl`](../../data/bench/rag-questions.jsonl)), dont 4 sans réponse
dans le corpus (le bon comportement est de le dire). Chaque question passe par le vrai moteur
de Sensai (`ChatEngine`, guardrails, persona, retriever). Une réponse est juste si elle contient
tous les mots-clés attendus (casse et accents ignorés).

```bash
uv run python -m sensai.eval.bench rag     # 3 min sur GPU, ~35 min sur CPU
```

**Résultats** (26/10/2026, RTX 4060, index : 26 chunks en 0,8 s, une recherche 24 ms) :

| Condition                 | Exactitude | Faits justes | Refus justes | Source citée   | Temps médian | 1er token | Tokens prompt |
| ------------------------- | ---------- | ------------ | ------------ | -------------- | ------------ | --------- | ------------- |
| A : sans RAG, persona     | 23 %       | 1/18         | 4/4          | 5/18 (fausses) | 1,3 s        | 0,2 s     | 289           |
| B : RAG, prompt générique | **82 %**   | 15/18        | 3/4          | 3/18           | 3,2 s        | 0,5 s     | 872           |
| C : RAG + persona         | **82 %**   | 15/18        | 3/4          | **15/18**      | 1,9 s        | 0,6 s     | 1 135         |

**À dire à l'oral** :

- RAG : **+59 points** d'exactitude (1 → 15 faits justes sur 18) pour ~600 tokens de prompt et
  0,3 s de plus avant le premier mot. C'est le compromis « précision vs latence » du critère 16.
- Sans documents, le modèle **invente des sources** : 5 réponses citent un fichier, dont
  `procedure-tri.md` qui n'existe pas, et un « poste 102 » inventé. Une citation ne prouve rien
  si la source n'était pas dans le prompt (hallucination à montrer en démo).
- Les 3 erreurs restantes viennent toutes d'un **tableau Markdown** (`calendrier-secteurs.md`) :
  le modèle lit la mauvaise ligne (13 h 00 est l'horaire du secteur D, pas du A). Piste :
  découper les documents par titres et garder l'en-tête des tableaux.
- Une question piège (« qui a lancé l'Opération Hérisson et en quelle année ? ») reçoit une
  réponse plausible au lieu d'un refus : le contexte proche pousse le modèle à combler les trous.

## A/B 2 : pré-prompt générique vs spécialisé

Mesuré par le même script (conditions B et C ci-dessus) : **même exactitude (82 %)**, mais la
persona fait citer la source **15 fois sur 18 au lieu de 3** et donne des réponses plus courtes
(1,9 s contre 3,2 s). La persona change la forme et la traçabilité, pas ce que le modèle sait.
Bascule en direct avec `/persona off` / `/persona on`.

## A/B 3 : compression du budget (M2)

Session longue (30 tours scriptés) avec `budget.max_tokens = 2048` vs compression désactivée.
Métriques : tokens de prompt au tour 30, latence au tour 30, et le modèle se souvient-il d'un fait
donné au tour 2 (oui / non). Montre le compromis « coût de contexte vs perte d'information ».

## A/B 4 : température

Questions 1 à 10, condition B, `temperature` 0.0 vs 0.7 vs 1.2, 5 passages chacune sans `seed`.
Métriques : exactitude moyenne et variance entre passages.

## Autres mesures

Vitesse des 10 modèles, choix des outils, effort de réflexion, limites de la fenêtre de
contexte : [../benchmarks.md](../benchmarks.md), résumé dans [modeles.md](modeles.md).

## Rejouer en direct

1. Préchauffer le modèle (voir [demo-script.md](demo-script.md#préparation-avant-dentrer-en-salle)).
2. Lancer `uv run python -m sensai.eval.bench rag` (3 minutes sur GPU).
3. Comparer aux résultats du tableau : les **ordres de grandeur** doivent tenir (écart d'exactitude
   de plusieurs dizaines de points), pas les valeurs exactes.
