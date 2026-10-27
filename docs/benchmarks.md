# Benchmarks

What is fast, what is slow, and where the models stop working.

**Machine**: Intel i7-13650HX (14 cores, 20 threads), 15 GB of RAM, NVIDIA RTX 4060 Laptop
(8 GB), Linux, Python 3.14, Ollama 0.40. Every model suite was run twice: on **CPU** (CPU-only
Ollama build, 2026-10-21) and on **GPU** (`ollama-cuda`, 2026-10-26, every model fully in
VRAM). Sensai's own figures do not depend on it.

Raw results (Markdown and JSON) are written to `reports/bench/` (not committed).
[Reproduce](#reproduce) at the end.

## In short

| Part                                    | GPU       | CPU      | Verdict                                            |
| --------------------------------------- | --------- | -------- | -------------------------------------------------- |
| Sensai's own work for one turn          | 0.25–5 ms | same     | Negligible                                         |
| Guardrails on one message               | ~32 µs    | same     | Negligible                                         |
| Start-up (import of the CLI)            | 216 ms    | same     | Fine (was 398 ms, fixed)                           |
| RAG vector search, 1 000 chunks         | 30 ms     | same     | Fine (was 232 ms, fixed)                           |
| qwen3.5:4b first token, short prompt    | 0.3 s     | 7.1 s    | GPU: instant. CPU: the bottleneck                  |
| qwen3.5:4b writing speed                | 37 tok/s  | 11 tok/s | GPU: faster than reading. CPU: slow                |
| qwen3.5:4b reading a full 8k window     | 3.5 s     | ~100 s   | CPU: 1.5 min before the first word                 |
| Thinking on (`/effort low`), simple sum | 50 s      | ~7 min   | **Too slow even on GPU**; off answers right in 3 s |
| RAG A/B, 66 questions                   | 3 min     | ~35 min  |                                                    |

Everything Sensai does around the model costs milliseconds; all the waiting is the model.
**The GPU makes a reply 5–14× faster end to end** (6.5× for qwen3.5:4b) (20–60× to read the prompt, 3–4× to write
the answer), and turns Sensai from "wait 10 seconds" into a normal chat.

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
(500–1 100 tokens in depending on the tokenizer, 128 out), temperature 0, thinking off, 1 cold
run then 3 warm runs.

| Model          | Params | Quant  | Size   | GPU read (tok/s) | GPU write (tok/s) | GPU 128-tok reply | CPU write (tok/s) | CPU 128-tok reply |
| -------------- | ------ | ------ | ------ | ---------------- | ----------------- | ----------------- | ----------------- | ----------------- |
| granite3.1-moe | 3.3B   | Q4_K_M | 2.4 GB | 4 713            | **146**           | **1.0 s**         | **46.2**          | **5.8 s**         |
| qwen3.5:2b     | 1.9B   | Q8_0   | 2.4 GB | 3 886            | 64                | 1.8 s             | 16.0              | 10.1 s            |
| gemma4:e4b     | 7.5B   | Q4_K_M | 1.8 GB | 1 576            | 64                | 1.6 s             | 16.2              | 14.4 s            |
| bonsai2        | 8.2B   | Q1_0   | 1.9 GB | 1 506            | 61                | 2.4 s             | 16.7              | 34.2 s            |
| llama3.2:3b    | 3.2B   | Q4_K_M | 2.6 GB | 3 099            | 49                | 2.3 s             | 15.7              | 11.9 s            |
| ministral-3:3b | 3.8B   | Q4_K_M | 2.7 GB | 5 627            | 44                | 2.9 s             | 13.9              | 14.0 s            |
| phi4-mini      | 3.8B   | Q4_K_M | 3.1 GB | 2 608            | 38                | 2.0 s             | 12.7              | 10.7 s            |
| qwen3.5:4b     | 4.2B   | Q4_K_M | 3.1 GB | 1 700            | 37                | 2.0 s             | 11.0              | 12.9 s            |
| mistral:7b     | 7.2B   | Q4_K_M | 5.0 GB | 1 141            | 23                | 6.2 s             | 7.6               | 31.7 s            |
| qwen3.5:9b     | 9.0B   | Q4_K_M | 6.2 GB | 984              | 20                | 4.7 s             | 6.4               | 25.6 s            |

Size is the memory used with an 8 192-token window (CPU run). First token on GPU: 0.1–0.6 s
for every model, against 3–27 s on CPU. Cold load (disk to memory): 1–6 s on both.

- **Reading gains much more than writing.** Reading the prompt is parallel work, which a GPU
  does 20–65× faster. Writing is one token at a time and limited by memory bandwidth: 3–4×.
- Writing speed follows the number of **active** parameters: granite is a mixture of experts
  (~0.8B active), so it writes 3× faster than dense 3–4B models; 7–9B models write at
  20–23 tokens/s on GPU, 6–8 on CPU.
- bonsai2 (1-bit) reads very slowly on CPU (23 tok/s, no optimized kernel) but normally on GPU.
- Every model fits in the 8 GB of VRAM; qwen3.5:9b (6.2 GB) leaves little room for a larger
  window.

## First token and VRAM: RTX 4070 follow-up

Measured on 2026-10-27, NVIDIA RTX 4070 Laptop GPU (8 GB), NVIDIA driver 580.178.04,
Ollama 0.34.3, on AC power. These are separate measurements from Alban's historical
RTX 4060 results above. Identical tags do not guarantee identical model revisions;
the new campaign records model digests and the parameter/quantization metadata actually
returned by Ollama.

Scope: the ten historical dialogue models plus `sensai-llama3.2` and `gemma3:4b`, for
twelve dialogue models. The defense table's eleventh historical row, `nomic-embed-text`,
is an embedding model and is not part of this first-token benchmark.

Same French summary prompt as the speed suite; `num_ctx = 8192`, `temperature = 0`,
`seed = 42`, thinking off where supported, at most 128 generated tokens. First token is
timed from the HTTP request to the first non-empty answer chunk. Warm figures are the
median of three calls with different prompt prefixes; cold is one call after unloading
the model (the operating system's disk cache is not cleared). VRAM is the sum of memory
allocated to Ollama processes reported by `nvidia-smi`, including CUDA overhead, after the
calls, in decimal GB. Only one model is loaded at a time. These are snapshots, not peaks.
Ollama's separate `size_vram` counter is retained in JSON for comparison: for `gemma4:e4b`
it returned an implausible 0.26 GB, so this table consistently uses the driver counter.

| Model                          | Params | Quant       | First token, warm median | First token, cold | VRAM, NVIDIA (GB) |
| ------------------------------ | ------ | ----------- | ------------------------ | ----------------- | ----------------- |
| granite3.1-moe                 | 3.3B   | Q4_K_M      | 0.094 s                  | 4.590 s           | 2.89              |
| qwen3.5:2b                     | 1.9B   | Q8_0        | 0.100 s                  | 6.111 s           | 3.30              |
| gemma4:e4b                     | 7.5B   | Q4_K_M      | 0.213 s                  | 14.299 s          | 4.98              |
| Bonsai 8B (official candidate) | 8.19B  | Q1_0 (tags) | 0.245 s                  | 7.062 s           | 2.66              |
| llama3.2:3b                    | 3.2B   | Q4_K_M      | 0.142 s                  | 4.081 s           | 3.27              |
| ministral-3:3b                 | 3.8B   | Q4_K_M      | 0.152 s                  | 4.551 s           | 4.23              |
| phi4-mini                      | 3.8B   | Q4_K_M      | 0.129 s                  | 4.580 s           | 3.87              |
| qwen3.5:4b                     | 4.2B   | Q4_K_M      | 0.238 s                  | 7.426 s           | 4.19              |
| mistral:7b                     | 7.2B   | Q4_K_M      | 0.284 s                  | 4.008 s           | 5.78              |
| qwen3.5:9b                     | 9.7B   | Q4_K_M      | 0.377 s                  | 8.826 s           | 6.86              |
| sensai-llama3.2                | 3.2B   | Q4_K_M      | 0.136 s                  | 2.193 s           | 3.27              |
| gemma3:4b                      | 3.9B   | Q4_K_M      | 0.205 s                  | 5.093 s           | 4.21              |

Raw samples, model identities and machine metadata are saved locally under
`reports/bench/2026-10-27-rtx4070/` (ignored by Git). Temporary model downloads are removed
after measurement; models installed before the campaign are preserved.

The historical alias `bonsai2` is not a public Ollama tag. The official
[PrismML Bonsai 8B Q1_0](https://huggingface.co/prism-ml/Bonsai-8B-gguf) matches its listed
8.2B parameter count and 1-bit format, so it is tested here under its explicit source name.
This is a candidate reconstruction: Alban's original digest and Modelfile are unknown.
The public [Bonsai 2](https://ollama.com/library/bonsai-2) family uses ternary weights and
is not substituted for the historical 8.2B Q1_0 entry.
The two models missing from Alban's table, `sensai-llama3.2` and
`gemma3:4b`, are included here for responsiveness and VRAM. Their additional quality checks
are reported in the [RAG and French follow-up](#added-models-rag-and-french-quality) below.

For Bonsai, `/api/ps` reports quantization as `unknown`, while `/api/tags` identifies
`Q1_0` (retained in `model.json`); the table uses that explicit metadata. Its recorded text
starts with English deliberation despite thinking being disabled: this measures first
visible text, not correctness or the arrival of a useful final answer.

## Added models: RAG and French quality

Follow-up on 2026-10-27 for `sensai-llama3.2:latest` and `gemma3:4b` only, on the same
RTX 4070 Laptop GPU (8 GB), AMD Ryzen 7 7840HS, Ollama 0.34.3. Their speed/VRAM figures
are in the first-token table above; this campaign completes their quality checks, not those
of all twelve dialogue models.

### RAG: the existing 22 questions and three conditions

The existing `data/bench/rag-questions.jsonl` corpus is replayed through `ChatEngine`, with
guardrails, context budget, retrieval and persona as selected by each condition. One fresh
conversation per question; `temperature = 0`, `seed = 42`, `num_ctx = 8192`, thinking off.
`nomic-embed-text` indexes the same `data/collecte/` corpus (26 chunks, default top 5).
There are 18 answerable and 4 unanswerable questions: 66 replies per model, 132 saved replies.

The score below is the existing automatic heuristic: all expected keyword groups must occur,
or a recognised refusal phrase for an unanswerable question. It does not establish full factual
correctness. `.md` mentions count 18 answerable questions only, and do not validate citations.

| Model           | Condition           | Keyword/refusal score | Facts | Refusals | `.md` mentioned |
| --------------- | ------------------- | --------------------- | ----- | -------- | --------------- |
| sensai-llama3.2 | no RAG, persona     | 5/22 (22.7%)          | 2/18  | 3/4      | 7/18            |
| sensai-llama3.2 | RAG, generic prompt | 15/22 (68.2%)         | 14/18 | 1/4      | 0/18            |
| sensai-llama3.2 | RAG, persona        | 17/22 (77.3%)         | 13/18 | 4/4      | 0/18            |
| gemma3:4b       | no RAG, persona     | 9/22 (40.9%)          | 5/18  | 4/4      | 12/18           |
| gemma3:4b       | RAG, generic prompt | 17/22 (77.3%)         | 14/18 | 3/4      | 1/18            |
| gemma3:4b       | RAG, persona        | 18/22 (81.8%)         | 14/18 | 4/4      | 14/18           |

Inspection of the RAG + persona answers shows limits hidden by those counters:

- Both answer **13 h 00** for sector A instead of the corpus's **5 h 30**.
- Llama mentions no `.md` file in its 18 answerable replies despite the persona asking for sources.
- Gemma mentions a `.md` file 14 times, but cites `securite-collecte.md` for the orange sticker,
  bulky-waste quota, biodegradable bags and Tilleuls roadworks, whose expected sources differ.
- On question 21, Gemma asserts that the operations manager launched Hérisson before saying
  the information is missing. The refusal phrase still makes the automatic test pass.

These are evaluation results, not changes to the assistant's model or prompt.

### Tool calling: capability and the existing ten cases

| Model           | Result                                                    | Limit observed                                                                                                   |
| --------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| sensai-llama3.2 | 9/10 choices correct; no tool on the four plain questions | Misses `remember_fact`                                                                                           |
| gemma3:4b       | Native tool calling unavailable through this Ollama model | Ollama advertises no `tools` capability; the suite skips the calls, so its raw 0/10 is not ten observed failures |

The tool-choice suite checks requested names/arguments without executing the tools. These
results therefore do not prove successful file writes, web searches or memory updates.

### French: six fixed tasks, saved answers and a qualitative review

`python -m sensai.eval.bench french` runs the same six prompts for every selected model,
with the system instruction « Tu es Sensai. Réponds en français. », no RAG and no collecte
persona. Settings: temperature 0, seed 42, context 8192, at most 512 output tokens, thinking
off where supported. None of the twelve replies reached that output limit.

The review checks three distinct aspects: French/comprehensibility, grammar/agreements, and
preservation of the requested task and meaning. Verdicts below concern task adherence:
**Conforms** means the task and supplied meaning are preserved; **Partial** flags a defect
or unsupported addition; **Off target** flags a different topic or incorrect core meaning.
This is a qualitative inspection of the saved replies, not an automatic linguistic score.

| Task                  | sensai-llama3.2 | gemma3:4b  | Observation                                                                                                                                   |
| --------------------- | --------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| explanation           | Off target      | Off target | Both define a ripeur as a fruit worker rather than the collection job.                                                                        |
| resident_message      | Partial         | Partial    | Llama: missing object in « vous avez sorti »; Gemma: awkward « non-passage de votre bac » and invented sign-off. Both add a day not supplied. |
| grammar               | Conforms        | Conforms   | Both produce « Les trois bennes jaunes sont arrivées en retard et les équipages sont fatigués. »                                              |
| summary               | Conforms        | Partial    | Llama preserves all key facts. Gemma also retains them but adds an unsupported purpose, « Pour faciliter le tri ».                            |
| professional_register | Off target      | Off target | Both switch to school results; Llama refuses unrelated exam advice, Gemma requests replacement of a grade report.                             |
| missing_information   | Conforms        | Conforms   | Both say the supplied text gives no telephone number, without inventing one.                                                                  |

All six replies from each model are understandable French. Both pass the targeted agreement
correction. This does not make their answers reliable: fluent wording masks the wrong job
definition and off-topic reformulation. Six tasks are a small test set, not a general ranking
of French proficiency. The RAG + persona conditions above assess the actual specialised context
separately from these generic language tasks.

### Evidence and replay

Raw responses, model digests and the qualitative case review are saved under
`reports/bench/2026-10-27-rtx4070/quality/` (ignored by Git): `rag.json`, `answers.jsonl`,
each model's `french.json`/`french.md` and `tools.json`, and `french-review.json`.
The French corpus is fixed in `eval/bench/models.py`; its answers are not automatically graded.
Replay requires the two dialogue models to be installed (`sensai-llama3.2` is the project's
custom model) and `nomic-embed-text` for retrieval. The two temporary downloads from this
campaign were removed after the tests, as requested.

```bash
ollama pull gemma3:4b
ollama pull nomic-embed-text
uv run python -m sensai.eval.bench french --models sensai-llama3.2:latest,gemma3:4b --out reports/bench/quality-replay/french
uv run python -m sensai.eval.bench tools --models sensai-llama3.2:latest,gemma3:4b --out reports/bench/quality-replay/tools
uv run python -m sensai.eval.bench rag --models sensai-llama3.2:latest --out reports/bench/quality-replay/llama
uv run python -m sensai.eval.bench rag --models gemma3:4b --out reports/bench/quality-replay/gemma
```

## Models: picking the right tool

`python -m sensai.eval.bench tools`: 10 prompts with Sensai's real tool list. 4 need no
tool (greeting, definition, sum, general knowledge), 6 need one (`read_file`, `list_dir`,
`write_file`, `web_search`, `remember_fact`, `run_python`). Thinking off. **The scores are
identical on CPU and GPU**, case by case; only the time changes.

| Model          | Right     | Tool on a plain question             | Missed tool         | Wrong tool                | Median GPU | Median CPU |
| -------------- | --------- | ------------------------------------ | ------------------- | ------------------------- | ---------- | ---------- |
| qwen3.5:4b     | **10/10** | 0                                    | 0                   | 0                         | 1.3 s      | 11.5 s     |
| gemma4:e4b     | **10/10** | 0                                    | 0                   | 0                         | 0.5 s      | 1.9 s      |
| qwen3.5:9b     | 9/10      | 0                                    | 1 (`remember_fact`) | 0                         | 2.3 s      | 19.4 s     |
| qwen3.5:2b     | 9/10      | 0                                    | 0                   | 1 (read instead of write) | 0.7 s      | 6.5 s      |
| ministral-3:3b | 9/10      | 0                                    | 1 (`write_file`)    | 0                         | 0.8 s      | 3.0 s      |
| bonsai2        | 9/10      | 0                                    | 1 (`remember_fact`) | 0                         | 0.7 s      | 3.8 s      |
| llama3.2:3b    | 6/10      | **4** (searches the web for "hello") | 0                   | 0                         | 0.5 s      | 2.0 s      |
| granite3.1-moe | 4/10      | 0                                    | **6** (never calls) | 0                         | 1.8 s      | 6.9 s      |
| mistral:7b     | 4/10      | 0                                    | **6**               | 0                         | 4.9 s      | 26.4 s     |
| phi4-mini      | 4/10      | 0                                    | **6**               | 0                         | 1.4 s      | 6.2 s      |

granite, mistral and phi4-mini never call a tool through Ollama's chat API: their 4 points are
the 4 questions that needed none. They are fine for plain chat, useless for an agent.
llama3.2:3b calls tools too eagerly. **qwen3.5:4b (the default) and gemma4:e4b are the only
models with a perfect score**; gemma4 is faster on these short prompts.

## Thinking effort

`python -m sensai.eval.bench effort`: one three-step sum ("3 rounds of 42 km, then 2 of
37 km") on qwen3.5:4b at each `/effort` level.

| Effort | Correct | GPU: thinking / tokens written / time | CPU: thinking / tokens written / time |
| ------ | ------- | ------------------------------------- | ------------------------------------- |
| off    | yes     | none / 28 / **2.9 s**                 | none / 131 / **16 s**                 |
| low    | yes     | 5 900 chars / 1 835 / 50 s            | 10 500 chars / 3 180 / 455 s          |
| medium | yes     | 5 900 chars / 1 835 / 50 s            | 10 500 chars / 3 180 / 407 s          |
| high   | yes     | 5 900 chars / 1 835 / 50 s            | 10 500 chars / 3 180 / 465 s          |

1. **qwen3.5 ignores the level.** Low, medium and high produce exactly the same thoughts:
   Ollama only maps levels for models that support them (gpt-oss); for qwen3.5 any level
   means "on". `/effort` is in practice an on/off switch with this model.
2. **Thinking costs 17× (GPU) to 28× (CPU) the time for the same answer.** Sensai's default
   effort is `low`, so the default model thinks on every question, including ones that need no
   reasoning: 50 s on GPU, about 7 minutes on CPU. See the [code review](code-review.md)
   (item 2: `think = false` by default).
3. Temperature 0 is not identical across backends: the same prompt gives different thoughts
   on CPU and GPU (3 180 against 1 835 tokens), with the same final answer.

## Context window limits

`python -m sensai.eval.bench context`: a long French text (the scenario's rule books) with one
fact ("le code du portail du dépôt est 4471") hidden at 10 %, 50 % or 90 % of it, on
qwen3.5:4b, for growing `num_ctx`.

| num_ctx | Prompt (real tokens) | Fact found (10/50/90 %) | GPU read speed | GPU 1st token | CPU read speed | CPU 1st token | Memory |
| ------- | -------------------- | ----------------------- | -------------- | ------------- | -------------- | ------------- | ------ |
| 2 048   | 1 681                | yes / yes / yes         | 1 910 tok/s    | 0.9 s         | 65 tok/s       | 25–33 s       | 3.1 GB |
| 4 096   | 3 233                | yes / yes / yes         | 1 910 tok/s    | 1.7 s         | 65 tok/s       | 48–54 s       | 3.1 GB |
| 8 192   | 6 447                | yes / yes / yes         | 1 860 tok/s    | 3.4 s         | 64 tok/s       | 101–107 s     | 3.4 GB |
| 16 384  | 12 830               | yes (50 %)              | 1 800 tok/s    | 9.1 s         | 56 tok/s       | 232 s         | 3.7 GB |
| 32 768  | 25 633               | yes (50 %)              | 1 590 tok/s    | **18 s**      | 46 tok/s       | **561 s**     | 4.2 GB |

GPU first-token times are for a model already loaded; the first call at a new window size also
reloads the model (about 2 s more).

- **Accuracy is not the limit**: the model finds the fact anywhere, up to 25 000 tokens, on
  both backends.
- **Time is the limit on CPU**: a full 8k window is about 100 s before the first word, 32k over
  9 minutes. On GPU, 32k is 18 s: usable.
- **Memory is not the limit**: 32k costs 1.1 GB more than 2k, and fits in the 8 GB of VRAM.
- **Token estimate**: Sensai's budget counts 4 characters per token; on French text the real
  ratio is 3.5–3.7, so the budget **underestimates by about 10 %** (code review item 6).

### Proof of the silent truncation (fixed)

The same ~5 900-token prompt with the fact at 5 %, sent once without `num_ctx` (Ollama's own
default) and once with Sensai's new default. Same result on CPU and on GPU: with 8 GB of VRAM,
Ollama's default window is still 4 096 tokens.

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
temperature 0, on the GPU (the whole suite takes 3 minutes, against about 35 on CPU).
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

| Question                    | GPU (RTX 4060)                                                                                 | CPU only                                     |
| --------------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------- |
| Best default model          | **qwen3.5:4b**: perfect tool choice, 37 tok/s                                                  | qwen3.5:4b, 11 tok/s; gemma4:e4b if too slow |
| Fastest model worth using   | gemma4:e4b (10/10 tools, 64 tok/s)                                                             | qwen3.5:2b or gemma4:e4b (9–10/10, 16 tok/s) |
| Models not to use as agents | granite3.1-moe, mistral:7b, phi4-mini (never call tools), llama3.2:3b (calls them for nothing) | same                                         |
| Largest useful window       | 32 768 tokens (18 s to read when full)                                                         | 8 192 tokens (~100 s when full)              |
| Thinking                    | Off by default; on for real multi-step problems (~50 s)                                        | Off; on costs minutes                        |
| RAG                         | 23 % → 82 % right answers, sources cited with the persona                                      | same accuracy, ~10× slower                   |
| Bigger model?               | qwen3.5:9b fits, but no gain in tool choice, half the speed                                    | same                                         |

## Reproduce

The speed suite now measures the first non-empty streamed answer text from request start
(rather than estimating it as load time plus prefill time). It fixes `num_ctx = 8192`
and reports Ollama's `size_vram` separately from total loaded memory. When `nvidia-smi` is
available, it also records the memory allocated to Ollama processes, including CUDA overhead.
Both are snapshots after the calls, not sampled peaks. Unavailable NVIDIA counters are
shown as missing, not zero. Historical figures above retain their original method and hardware.
The local NVIDIA counter is omitted when `--base-url` points to a remote Ollama server.

The first call follows a model unload; it does not clear the operating system's disk cache.
Three subsequent calls supply the warm median. Their prompts have different prefixes to
avoid reusing the prompt cache. JSON results retain all four samples, and each completed
model is saved under `models/` before the next starts. Use a separate `--out` directory for
each machine or campaign to keep earlier results.

```bash
uv run python -m sensai.eval.bench perf                      # ~5 s, no model
uv run python -m sensai.eval.bench speed                     # every installed model: 2.5 min GPU, 12 min CPU
uv run python -m sensai.eval.bench tools --models qwen3.5:4b # one model
uv run python -m sensai.eval.bench effort                    # 2.5 min GPU, 25 min CPU
uv run python -m sensai.eval.bench context --sizes 2048,8192 # all sizes: 1 min GPU, 25 min CPU
uv run python -m sensai.eval.bench rag                       # 3 min GPU, 35 min CPU
```

Every suite prints a table and writes `reports/bench/<suite>.md` and `.json`. Model suites
exit with code 2 and one line if Ollama is not running. The full run takes about 12 minutes on
the GPU and 1.5 h on CPU; on CPU, close other heavy programs first (it once got Ollama killed
by the out-of-memory killer, which is why the RAG suite retries a dropped call once).

Using the GPU on Arch: install `ollama-cuda` at **the same version** as `ollama` (a mismatch
makes every model load crash with a segmentation fault), restart the service, then check with
`/ps` in Sensai or `ollama ps` that the model shows `100% GPU`.
