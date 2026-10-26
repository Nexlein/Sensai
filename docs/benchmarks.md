# Benchmarks

What is fast, what is slow, and where the models stop working. Measured on 2026-10-21.

**Machine**: Intel i7-13650HX (14 cores, 20 threads), 15 GB of RAM, Linux, Python 3.14.
Ollama 0.40 **CPU-only build** for every model figure except the RAG A/B: the laptop's
RTX 4060 (8 GB) was not used. The RAG A/B was run on 2026-10-26 after installing the CUDA
build (`ollama-cuda` on Arch), model fully on the GPU. Sensai's own figures do not depend on it.

Raw results (Markdown and JSON) are written to `reports/bench/` (not committed).
[Reproduce](#reproduce) at the end.

## In short

| Part                             | Time                          | Verdict                                                     |
| -------------------------------- | ----------------------------- | ----------------------------------------------------------- |
| Sensai's own work for one turn   | 0.25–5 ms                     | Negligible, 1 000× below the model                          |
| Guardrails on one message        | ~32 µs                        | Negligible                                                  |
| Start-up (import of the CLI)     | 216 ms                        | Fine (was 398 ms, fixed)                                    |
| RAG vector search, 1 000 chunks  | 30 ms                         | Fine (was 232 ms, fixed); about 140 ms at 5 000 chunks      |
| Model: first token, short prompt | 3–15 s                        | **The bottleneck**, depends on the model                    |
| Model: writing the reply         | 6–46 tokens/s                 | **The bottleneck**: a 128-token reply takes 6–32 s          |
| Model: reading a full 8k window  | ~100 s (qwen3.5:4b)           | **Slow**: a full window means 1.5 min before the first word |
| Thinking on (`/effort low`)      | ~7 min for a sum (qwen3.5:4b) | **Far too slow on CPU**; off answers right in 16 s          |

Everything Sensai does around the model costs milliseconds. All of the waiting comes from the
model, and on this machine from running it on the CPU.

## Sensai's own code

`python -m sensai.eval.bench perf`, idle CPU, median of 5 runs. Model replaced by the mock.

| Area       | Operation                                  | Size         | Median       |
| ---------- | ------------------------------------------ | ------------ | ------------ |
| startup    | import the CLI entry point (new process)   | -            | 216 ms       |
| startup    | build a session (mock model, no RAG/MCP)   | -            | 382 µs       |
| guardrails | input filter (injection + personal data)   | 130 chars    | 32 µs        |
| guardrails | input filter                               | 10 kB        | 2.2 ms       |
| guardrails | streamed reply filter, per chunk           | 1 chunk      | 5 µs         |
| engine     | full turn, guardrails off / on             | 50 words     | 252 / 495 µs |
| engine     | full turn, guardrails off / on             | 500 words    | 2.3 / 5.0 ms |
| prompt     | compose the prompt (budget + system notes) | 200 msgs     | 75 µs        |
| prompt     | compose the prompt                         | 2 000 msgs   | 645 µs       |
| tools      | `write_file` preview diff                  | 1 000 lines  | 466 µs       |
| memory     | save session (every turn)                  | 200 msgs     | 496 µs       |
| memory     | save session                               | 2 000 msgs   | 5.5 ms       |
| memory     | format facts for the prompt                | 20 facts     | 2.9 ms       |
| rag        | chunk the documents                        | 112 kB       | 675 µs       |
| rag        | vector search                              | 100 chunks   | 3.1 ms       |
| rag        | vector search                              | 1 000 chunks | 30 ms        |
| rag        | vector search                              | 5 000 chunks | 142 ms       |
| config     | load / save `sensai.toml` (keeps comments) | -            | 35 / 214 µs  |
| config     | `/config show`                             | 41 keys      | 129 µs       |

Two items were slow enough to fix in this branch:

- **Start-up**: the CLI imported Textual and FastAPI even for the plain CLI. 398 → 216 ms
  (they are now imported only when `--ui tui` or `--ui web` is chosen).
- **Vector search**: every query JSON-decoded every vector. Vectors are now packed doubles,
  scored with a C dot product, and only the top chunks are fetched: 232 → 30 ms for 1 000
  chunks, same results.

Things that grow without limit but stay small in practice: saving a session rewrites all its
messages (5.5 ms at 2 000 messages), vector search is linear in the number of chunks (fine
up to ~10 000 chunks; past that an index such as `sqlite-vec` would be needed).

## Models: speed and memory

`python -m sensai.eval.bench speed`: every installed model, the same French text to summarize
(500–1 100 tokens in depending on the tokenizer, 128 out), temperature 0, thinking off, 1 cold run then 3 warm runs.

| Model          | Params | Quant  | RAM    | Cold load | Read (tok/s) | Write (tok/s) | 1st token | 128-tok reply |
| -------------- | ------ | ------ | ------ | --------- | ------------ | ------------- | --------- | ------------- |
| granite3.1-moe | 3.3B   | Q4_K_M | 2.4 GB | 1.8 s     | 238          | **46.2**      | 3.0 s     | **5.8 s**     |
| qwen3.5:2b     | 1.9B   | Q8_0   | 2.4 GB | 2.1 s     | 141          | 16.0          | 3.7 s     | 10.1 s        |
| phi4-mini      | 3.8B   | Q4_K_M | 3.1 GB | 2.4 s     | 92           | 12.7          | 5.4 s     | 10.7 s        |
| llama3.2:3b    | 3.2B   | Q4_K_M | 2.6 GB | 2.1 s     | 111          | 15.7          | 5.7 s     | 11.9 s        |
| qwen3.5:4b     | 4.2B   | Q4_K_M | 3.1 GB | 3.1 s     | 74           | 11.0          | 7.1 s     | 12.9 s        |
| ministral-3:3b | 3.8B   | Q4_K_M | 2.7 GB | 2.6 s     | 190          | 13.9          | 5.9 s     | 14.0 s        |
| gemma4:e4b     | 7.5B   | Q4_K_M | 1.8 GB | 6.2 s     | 62           | 16.2          | 8.6 s     | 14.4 s        |
| qwen3.5:9b     | 9.0B   | Q4_K_M | 6.2 GB | 4.6 s     | 41           | 6.4           | 12.8 s    | 25.6 s        |
| mistral:7b     | 7.2B   | Q4_K_M | 5.0 GB | 3.2 s     | 44           | 7.6           | 14.8 s    | 31.7 s        |
| bonsai2        | 8.2B   | Q1_0   | 1.9 GB | 1.0 s     | 23           | 16.7          | 27.2 s    | 34.2 s        |

- Reply speed follows the number of **active** parameters: granite is a mixture of experts
  (~0.8B active), so it writes 3–4× faster than dense 3–4B models; 7–9B models write at
  6–8 tokens/s, slower than reading speed.
- bonsai2 (1-bit) is small in RAM but reads very slowly on CPU (no optimized kernel).
- Every model fits in RAM; on the 8 GB GPU all of them except qwen3.5:9b with a large window
  would fit too.

## Models: picking the right tool

`python -m sensai.eval.bench tools`: 10 prompts with Sensai's real tool list. 4 need no
tool (greeting, definition, sum, general knowledge), 6 need one (`read_file`, `list_dir`,
`write_file`, `web_search`, `remember_fact`, `run_python`). Thinking off.

| Model          | Right     | Tool on a plain question             | Missed tool         | Wrong tool                | Median time |
| -------------- | --------- | ------------------------------------ | ------------------- | ------------------------- | ----------- |
| qwen3.5:4b     | **10/10** | 0                                    | 0                   | 0                         | 11.5 s      |
| gemma4:e4b     | **10/10** | 0                                    | 0                   | 0                         | 1.9 s       |
| qwen3.5:9b     | 9/10      | 0                                    | 1 (`remember_fact`) | 0                         | 19.4 s      |
| qwen3.5:2b     | 9/10      | 0                                    | 0                   | 1 (read instead of write) | 6.5 s       |
| ministral-3:3b | 9/10      | 0                                    | 1 (`write_file`)    | 0                         | 3.0 s       |
| bonsai2        | 9/10      | 0                                    | 1 (`remember_fact`) | 0                         | 3.8 s       |
| llama3.2:3b    | 6/10      | **4** (searches the web for "hello") | 0                   | 0                         | 2.0 s       |
| granite3.1-moe | 4/10      | 0                                    | **6** (never calls) | 0                         | 6.9 s       |
| mistral:7b     | 4/10      | 0                                    | **6**               | 0                         | 26.4 s      |
| phi4-mini      | 4/10      | 0                                    | **6**               | 0                         | 6.2 s       |

granite, mistral and phi4-mini never call a tool through Ollama's chat API: their 4 points are
the 4 questions that needed none. They are fine for plain chat, useless for an agent.
llama3.2:3b calls tools too eagerly. **qwen3.5:4b (the default) and gemma4:e4b are the only
models with a perfect score**; gemma4 is faster on these short prompts.

## Thinking effort

`python -m sensai.eval.bench effort`: one three-step sum ("3 rounds of 42 km, then 2 of
37 km") on qwen3.5:4b at each `/effort` level.

| Effort | Correct | Thinking     | Tokens written | Time     |
| ------ | ------- | ------------ | -------------- | -------- |
| off    | yes     | none         | 131            | **16 s** |
| low    | yes     | 10 500 chars | 3 180          | 455 s    |
| medium | yes     | 10 500 chars | 3 180          | 407 s    |
| high   | yes     | 10 500 chars | 3 180          | 465 s    |

Two findings:

1. **qwen3.5 ignores the level.** Low, medium and high produce exactly the same thoughts:
   Ollama only maps levels for models that support them (gpt-oss); for qwen3.5 any level
   means "on". `/effort` is in practice an on/off switch with this model.
2. **Thinking costs 25× the time for the same answer.** On CPU, 3 000 thinking tokens is
   about 7 minutes. Sensai's default effort is `low`, so a first-time user of the default
   model waits minutes on questions that need no reasoning. See the
   [code review](code-review.md) for the recommendation (`think = false` by default on CPU).

## Context window limits

`python -m sensai.eval.bench context`: a long French text (the scenario's rule books) with one
fact ("le code du portail du dépôt est 4471") hidden at 10 %, 50 % or 90 % of it, on
qwen3.5:4b, for growing `num_ctx`.

| num_ctx | Prompt (real tokens) | Fact found (10/50/90 %) | Read speed | 1st token | RAM    |
| ------- | -------------------- | ----------------------- | ---------- | --------- | ------ |
| 2 048   | 1 681                | yes / yes / yes         | 65 tok/s   | 25–33 s   | 3.1 GB |
| 4 096   | 3 233                | yes / yes / yes         | 65 tok/s   | 48–54 s   | 3.1 GB |
| 8 192   | 6 447                | yes / yes / yes         | 64 tok/s   | 101–107 s | 3.4 GB |
| 16 384  | 12 830               | yes (50 %)              | 56 tok/s   | 232 s     | 3.7 GB |
| 32 768  | 25 633               | yes (50 %)              | 46 tok/s   | **561 s** | 4.2 GB |

- **Accuracy is not the limit**: the model finds the fact anywhere, up to 25 000 tokens.
- **Time is the limit**: reading slows as the window grows, and a full 32k prompt takes over
  9 minutes before the first word on CPU. A full 8k window takes about 100 s.
- **Memory is not the limit**: 32k costs 1.1 GB more than 2k.
- **Token estimate**: Sensai's budget counts 4 characters per token; on French text the real
  ratio is 3.5–3.7, so the budget **underestimates by about 10 %** (code review item 6).

### Proof of the silent truncation (fixed)

The same ~5 900-token prompt with the fact at 5 %, sent once without `num_ctx` (Ollama's own
default) and once with Sensai's new default:

| num_ctx sent         | Window used by Ollama | Tokens kept | Fact found |
| -------------------- | --------------------- | ----------- | ---------- |
| none (old behaviour) | 4 096                 | 2 050       | **no**     |
| 8 192 (new default)  | 8 192                 | 5 907       | yes        |

Without `num_ctx`, Ollama cut the prompt to fit 4 096 tokens and dropped its beginning, where
Sensai puts the persona and system notes, with no error. Sensai's budget allowed 8 192 tokens,
so it never noticed. `options.num_ctx` now defaults to 8 192.

## RAG and persona A/B

`python -m sensai.eval.bench rag`: 22 questions about the demo corpus (`data/collecte/`),
18 answerable (keywords a right answer must contain) and 4 not in the documents (the right
answer is "I can't find it"). Run through Sensai's real engine, qwen3.5:4b, thinking off,
temperature 0, **on the GPU** (the whole suite takes 3 minutes, against about 35 on CPU).
Index: 26 chunks in 0.8 s, one retrieval 24 ms.

| Condition           | Accuracy | Facts right | Refusals right | Source cited | Median time | 1st token | Prompt tokens |
| ------------------- | -------- | ----------- | -------------- | ------------ | ----------- | --------- | ------------- |
| no RAG, persona     | 23 %     | 1/18        | 4/4            | 5/18 (fake)  | 1.3 s       | 0.2 s     | 289           |
| RAG, generic prompt | **82 %** | 15/18       | 3/4            | 3/18         | 3.2 s       | 0.5 s     | 872           |
| RAG, persona        | **82 %** | 15/18       | 3/4            | **15/18**    | 1.9 s       | 0.6 s     | 1 135         |

- **RAG: 23 % → 82 %** (facts 1/18 → 15/18) for about 600 more prompt tokens and 0.3 s more
  before the first word. That is the main measured improvement.
- **Persona: same accuracy, sources cited 3 → 15 out of 18**, and shorter, faster answers
  (1.9 s against 3.2 s). The persona changes the form, not what the model knows.
- **Without RAG the model invents sources.** With the persona and no documents it mostly says
  "je ne trouve pas", but 5 answers cite a file anyway, including `procedure-tri.md`, which does
  not exist, and an invented phone extension ("poste 102"). A cited source is only proof when
  the source was really in the prompt.
- **The 3 misses all come from one Markdown table** (`calendrier-secteurs.md`): the model reads
  the wrong row (secteur A "13 h 00" is secteur D's time) or misses the sentence above the
  table. Tables cut by characters lose their header (code review item 5).
- **One trap question fails with RAG**: "who launched Opération Hérisson, and in which year?"
  gets a plausible "the operations manager" instead of a refusal. Retrieved text about a topic
  makes the model answer questions next to it that the text does not settle.

## What this means for the models

| Question                    | Answer on this machine (CPU)                                                                   |
| --------------------------- | ---------------------------------------------------------------------------------------------- |
| Best default model          | **qwen3.5:4b**: perfect tool choice, 3 GB, ~11 tokens/s. gemma4:e4b is the alternative.        |
| Fastest model worth using   | qwen3.5:2b (9/10 tools, 16 tokens/s, 2.4 GB)                                                   |
| Models not to use as agents | granite3.1-moe, mistral:7b, phi4-mini (never call tools), llama3.2:3b (calls them for nothing) |
| Largest useful window       | 8 192 tokens (~100 s to read when full); 16k works but takes 4 min                             |
| Thinking                    | Off by default on CPU; on only for real multi-step problems                                    |
| RAG                         | 23 % → 82 % right answers, sources cited when the persona is on                                |
| Bigger model?               | qwen3.5:9b: no gain in tool choice, half the speed                                             |
| What would change it all    | Using the GPU (CUDA build of Ollama)                                                           |

## Reproduce

```bash
uv run python -m sensai.eval.bench perf                      # ~5 s, no model
uv run python -m sensai.eval.bench speed                     # every installed model, ~12 min
uv run python -m sensai.eval.bench tools --models qwen3.5:4b # one model
uv run python -m sensai.eval.bench effort                    # ~25 min on CPU
uv run python -m sensai.eval.bench context --sizes 2048,8192 # ~25 min for all sizes
uv run python -m sensai.eval.bench rag                       # ~35 min on CPU, 3 min on GPU
```

Every suite prints a table and writes `reports/bench/<suite>.md` and `.json`. Model suites
exit with code 2 and one line if Ollama is not running. Close other heavy programs first: the
full run (about 1.5 h on CPU) once got Ollama killed by the out-of-memory killer, which is why
the RAG suite retries a dropped call once.
