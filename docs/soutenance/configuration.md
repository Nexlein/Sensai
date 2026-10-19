# Configuration

Toute la configuration passe par `sensai.toml` (ignoré par Git), avec la priorité
**argument CLI > `sensai.toml` > valeur par défaut** (`core/config.py`, `load_config`).
Une valeur invalide donne une `ConfigError` en une ligne, jamais une trace Python.

## Ce qui existe aujourd'hui

Exemple complet, valeurs par défaut sauf mention :

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

Le RAG s'active en ligne de commande uniquement :

```bash
uv run sensai chat --rag-dir data/collecte --rag-model nomic-embed-text --rag-db rag.db
```

Modification en direct, sans redémarrer :

```text
/config get guardrails
/config set model llama3.2
/effort
/config save
```

### Bascules de features

| Feature              | Bascule actuelle                  | Manque                                |
| -------------------- | --------------------------------- | ------------------------------------- |
| Guardrails (EV2)     | `[guardrails] enabled`            | —                                     |
| Mémoire (M3)         | `[memory] enabled`                | —                                     |
| Raisonnement (A1)    | `[reasoning] enabled`             | —                                     |
| Outils fichiers (T4) | `[tools] fs_allowed_root = false` | —                                     |
| MCP (T1)             | présence de `[mcp.servers.*]`     | —                                     |
| Log des réponses     | `[eval] log_replies`              | —                                     |
| RAG (R1)             | `--rag-dir` (CLI seulement)       | section `[rag]`                       |
| Recherche web (T3)   | toujours enregistrée              | `[tools] web_search = false`          |
| Sandbox (T2)         | toujours enregistrée              | `[tools] sandbox = false`             |
| Budget (M2)          | toujours actif                    | `[budget] enabled` (utile pour l'A/B) |

## Température et contexte

Sans champ `options`, Ollama applique les valeurs du Modelfile du modèle, ou ses défauts. Or notre
budget suppose 8192 tokens, alors que le `num_ctx` par défaut d'Ollama est plus petit selon la
version (2048 ou 4096). Au-delà, **Ollama tronque silencieusement le début du prompt**,
c'est-à-dire nos messages système (persona, RAG, privacy note). Le modèle « oublie » ses règles
sans erreur.

Section `[options]` (le nom `[model]` est impossible : la clé `model = "..."` existe déjà au
niveau racine du TOML). Chaque clé est facultative ; une clé absente n'est pas envoyée, et sans
section la requête est inchangée :

```toml
[options]
temperature = 0.2     # 0 = déterministe, 1+ = créatif
num_ctx = 8192        # taille de la fenêtre de contexte, en tokens
top_p = 0.9
seed = 42             # rend les benchmarks rejouables
num_predict = 512     # longueur max de la réponse
```

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
| `temperature` | Même question 5 fois à 0.0, puis à 1.2, `seed` non fixé | 0.0 : réponses identiques. 1.2 : formulations variées, plus d'inventions                                              |
| `temperature` | Prompt factuel du corpus à 0.0 et 1.2                   | Exactitude qui baisse avec la température (mesurable avec le bench)                                                   |
| `num_ctx`     | 2048 vs 8192 avec RAG `top_k = 5` et une longue session | 2048 : le modèle perd la persona et les sources ; 8192 : RAM plus haute (`ollama ps`)                                 |
| `num_ctx`     | Mesure mémoire                                          | Le cache KV grossit linéairement avec `num_ctx` (calcul dans [modeles.md](modeles.md#cache-kv-et-taille-du-contexte)) |
| `num_ctx`     | Temps avant le premier token avec un long prompt        | Plus de contexte = plus de `prompt_eval_duration`                                                                     |

Pour la démo, prévoir `/config set options.temperature 1.2` et `/config set options.num_ctx 2048`
en direct (avec `budget.max_tokens` ≤ 2048), puis rejouer la même question. Le changement
s'applique au tour suivant ; `/config set options.<clé> none` le retire, `/config save` l'écrit
dans `sensai.toml`.

## Profils par modèle

Une config n'est pas universelle : chaque modèle a sa fenêtre native, son format d'outils et sa
sensibilité à la température. Profils proposés (fichiers `profiles/<nom>.toml` ou sections à copier) :

| Profil                | `model`           | `num_ctx` | `temperature` | `think` | Pourquoi                                                     |
| --------------------- | ----------------- | --------- | ------------- | ------- | ------------------------------------------------------------ |
| Défaut (CPU, 16 Go)   | `qwen3.5:4b`      | 8192      | 0.2           | `"low"` | Outils fiables, français correct, tient en RAM               |
| Machine faible (8 Go) | `qwen3.5:4b` Q4   | 4096      | 0.2           | `false` | Moins de cache KV ; pas de raisonnement pour gagner du temps |
| Llama 3.2 3B          | `sensai-llama3.2` | 8192      | 0.2           | `null`  | Modelfile dédié (`ollama/Modelfile`), pas de mode thinking   |
| Juge (EV1)            | modèle plus gros  | 8192      | 0.0           | `null`  | Notation stable et rejouable                                 |
| Démo créativité       | identique         | identique | 1.2           | —       | Uniquement pour montrer l'effet de la température            |

`budget.max_tokens` suit `num_ctx` dans chaque profil.
