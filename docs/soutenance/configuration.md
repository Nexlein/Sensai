# Configuration

Toute la configuration passe par `sensai.toml` (ignoré par Git), avec la priorité
**argument CLI > `sensai.toml` > valeur par défaut** (`core/config.py`, `load_config`).
Une valeur invalide donne une `ConfigError` en une ligne, jamais une trace Python.

## Ce qui existe aujourd'hui

Exemple détaillé (`interface = "web"` est un choix pour la démo ; le défaut est `cli`).
La référence complète des clés est dans [../configuration.md](../configuration.md) :

```toml
interface = "web"                  # cli | tui | web
provider = "ollama"                # ollama | groq | mock
model = "qwen3.5:4b"
base_url = "http://localhost:11434"

[tools]
fs_allowed_root = "."              # false = outils fichiers désactivés

[budget]                           # M2 : compression de l'historique
max_tokens = 8192
threshold = 0.8                    # résume les vieux tours à 80 % du budget
keep_recent_turns = 4

[guardrails]                       # EV2
enabled = true
injection = "block"                # block | flag
pii = "redact"                     # redact | block

[memory]                           # M3
enabled = true
auto_inject = true

[reasoning]                        # A1 ReAct
enabled = true
show_thoughts = false
max_steps = 5
think = "low"                      # effort, modifiable en direct avec /effort

[eval]                             # EV1
log_replies = false
replies_path = "logs/replies.jsonl"
```

Le RAG et les outils web/sandbox se pilotent aussi depuis le fichier :

Les clés `[tools]` ci-dessous complètent la section déjà définie ; ne pas créer une seconde
table `[tools]` dans le même fichier TOML.

```toml
[rag]                              # R1, désactivé par défaut
enabled = true
dir = "data/collecte"
model = "nomic-embed-text"
db = "rag.db"
top_k = 5                          # chunks injectés par question
chunk_size = 500                   # caractères par chunk
chunk_overlap = 50                 # doit rester < chunk_size

[tools]
web_search = true                  # T3, false = outil retiré du registre
sandbox = true                     # T2 (run_python)
```

Les drapeaux CLI restent prioritaires sur le fichier ; `--rag-dir` active le RAG à lui seul :

```bash
uv run sensai chat --rag-dir data/collecte --rag-model nomic-embed-text --rag-db rag.db
```

Modification en direct, sans redémarrer, **enregistrée aussitôt** dans `sensai.toml`
(`autosave = true` par défaut, commentaires du fichier conservés) :

```text
/config                                  # tous les réglages, avec leur source (default, file, flag, session)
/config keys options                     # type, défaut et rôle de chaque réglage
/config set options.temperature 0.7      # options.temperature = 0.7 (saved to sensai.toml)
/config set options.num_ctx 2048         # refusé en une ligne : budget.max_tokens ne tient plus
/config reset options.temperature        # retour au défaut, clé retirée du fichier
/model llama3.2:3b                       # même chemin : validé, appliqué, enregistré
```

Depuis le terminal : `sensai config init` (fichier documenté avec tous les réglages),
`sensai config set <clé> <valeur>`, `sensai config keys`. Référence complète :
[../configuration.md](../configuration.md).

### Bascules de features

| Feature              | Bascule actuelle                  | Manque                                |
| -------------------- | --------------------------------- | ------------------------------------- |
| Guardrails (EV2)     | `[guardrails] enabled`            | —                                     |
| Mémoire (M3)         | `[memory] enabled`                | —                                     |
| Raisonnement (A1)    | `[reasoning] enabled`             | —                                     |
| Outils fichiers (T4) | `[tools] fs_allowed_root = false` | —                                     |
| MCP (T1)             | présence de `[mcp.servers.*]`     | —                                     |
| Log des réponses     | `[eval] log_replies`              | —                                     |
| RAG (R1)             | `[rag] enabled` ou `--rag-dir`    | —                                     |
| Recherche web (T3)   | `[tools] web_search = false`      | —                                     |
| Sandbox (T2)         | `[tools] sandbox = false`         | —                                     |
| Budget (M2)          | toujours actif                    | `[budget] enabled` (utile pour l'A/B) |

## Température et contexte

Sans champ `options`, Ollama applique les valeurs du Modelfile du modèle, ou ses défauts. Or notre
budget suppose 8192 tokens, alors que le `num_ctx` par défaut d'Ollama est de 4096 sur une
machine sans GPU. Au-delà, **Ollama tronque silencieusement le début du prompt**,
c'est-à-dire nos messages système (persona, RAG, privacy note). Le modèle « oublie » ses règles
sans erreur. **Corrigé** : `options.num_ctx` vaut 8192 par défaut et est toujours envoyé
(mesure dans [benchmarks.md](benchmarks.md)).

Section `[options]` (le nom `[model]` est impossible : la clé `model = "..."` existe déjà au
niveau racine du TOML). Les autres clés absentes ne sont pas envoyées ; `num_ctx = 8192`
reste envoyé par défaut, même sans cette section :

```toml
[options]
temperature = 0.2     # 0 = déterministe, 1+ = créatif
num_ctx = 8192        # taille de la fenêtre de contexte, en tokens
top_p = 0.9
seed = 42             # rend les benchmarks rejouables
num_predict = 512     # longueur max de la réponse
```

Avec `num_predict = 512` et `num_ctx = 8192`, régler aussi `[budget] max_tokens = 7680`
au plus, sinon la validation refuse cette combinaison.

Envoyée telle quelle dans la requête :

```json
{
  "model": "qwen3.5:4b",
  "messages": [...],
  "stream": true,
  "options": { "temperature": 0.2, "num_ctx": 8192, "top_p": 0.9, "seed": 42, "num_predict": 512 }
}
```

Groq reçoit `temperature`, `top_p`, `seed` et `num_predict` (en `max_tokens`) ; il gère seul sa
fenêtre, `num_ctx` ne lui est pas envoyé.

Règle de cohérence : `budget.max_tokens` doit valoir au plus `options.num_ctx - num_predict`, sinon
la réponse n'a plus de place. `AppConfig` le vérifie au chargement (`ConfigError` en une ligne) et
`/config set options.*` refuse une valeur incohérente.

### Observer l'impact (à montrer au jury)

| Paramètre     | Expérience                                              | Ce qu'on observe                                                                                                      |
| ------------- | ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `temperature` | Même question 5 fois à 0.0, puis à 1.2, `seed` non fixé | Observer la variabilité et les inventions éventuelles (essai à faire)                                                 |
| `temperature` | Prompt factuel du corpus à 0.0 et 1.2                   | Comparer l'exactitude ; effet non encore mesuré                                                                       |
| `num_ctx`     | 2048 vs 8192 avec RAG `top_k = 5` et une longue session | Comparer la mémoire et la conservation des informations ; cet essai précis reste à faire                              |
| `num_ctx`     | Mesure mémoire                                          | Le cache KV grossit linéairement avec `num_ctx` (calcul dans [modeles.md](modeles.md#cache-kv-et-taille-du-contexte)) |
| `num_ctx`     | Temps avant le premier token avec un long prompt        | Plus de contexte = plus de `prompt_eval_duration`                                                                     |

Pour la démo, prévoir `/config set options.temperature 1.2` et `/config set options.num_ctx 2048`
en direct (avec `budget.max_tokens` ≤ `2048 - num_predict`, ou 2048 si `num_predict` est absent), puis rejouer la même question. Le changement
s'applique au tour suivant ; `/config set options.<clé> none` le retire, `/config save` l'écrit
dans `sensai.toml`.

## Profils par modèle

Une config n'est pas universelle : chaque modèle a sa fenêtre native, son format d'outils et sa
sensibilité à la température. Profils proposés (fichiers `profiles/<nom>.toml` ou sections à copier) :

| Profil                | `model`           | `num_ctx` | `temperature` | `think` | Pourquoi                                                     |
| --------------------- | ----------------- | --------- | ------------- | ------- | ------------------------------------------------------------ |
| CPU conseillé (16 Go) | `qwen3.5:4b`      | 8192      | 0.2           | `false` | Évite la longue réflexion par défaut du code                 |
| Machine faible (8 Go) | `qwen3.5:4b` Q4   | 4096      | 0.2           | `false` | Moins de cache KV ; pas de raisonnement pour gagner du temps |
| Llama 3.2 3B          | `sensai-llama3.2` | 8192      | 0.2           | `null`  | Modelfile dédié (`ollama/Modelfile`), pas de mode thinking   |
| Juge (EV1)            | modèle plus gros  | 8192      | 0.0           | `null`  | Notation stable et rejouable                                 |
| Démo créativité       | identique         | identique | 1.2           | —       | Uniquement pour montrer l'effet de la température            |

`budget.max_tokens` reste au plus égal à `num_ctx - num_predict` dans chaque profil
(ou `num_ctx` si `num_predict` est absent).
