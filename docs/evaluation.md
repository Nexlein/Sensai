# Evaluation

Two offline tools check the assistant's quality. Neither runs during chat.

| Tool                    | Story | What it checks                                                     | Needs Ollama |
| ----------------------- | ----- | ------------------------------------------------------------------ | ------------ |
| Adversarial suite       | EV4   | Whether the guardrails stop jailbreaks, injections and PII leaks   | No           |
| LLM-as-judge            | EV1   | Whether a reply is relevant, coherent and backed by its sources    | Yes          |

## Adversarial suite (EV4)

Replays a corpus of attacks (`src/sensai/eval/adversarial/corpus.py`) against the guardrails, twice:

- **guardrail level**: the filters alone.
- **engine level**: through a real `ChatEngine` with a fake provider. It also checks that a blocked message never reaches the provider or the history, and that a masked value never survives in either.

```bash
uv run python -m sensai.eval.adversarial
```

```
== guardrail level ==
category          total  pass  fail  gaps
jailbreak             5     4     0     1
prompt_injection     13     8     0     5
...
detection rate: 75%
false positives: 11%
```

- **pass**: the guardrail did what the case expects.
- **fail**: it did not. The case id and the reason are printed under the table.
- **gaps**: `known_gap` cases, attacks the heuristics are known to miss, each with a reason in the corpus. They do not fail the run.
- **detection rate**: share of hostile cases handled as expected.
- **false positives**: share of harmless messages the guardrail touched.

Exit code: `0` when every case passes or is a known gap, `1` on a `fail` or on a stale gap (a `known_gap` that now passes: remove its `known_gap` mark).

### Adding a case

Append an `AttackCase` to the corpus with its expected verdict in `expect` (`block`, `redact`, `flag` or `allow`). Optionally set `rule` (the finding that must fire), `secret` (a value that must not survive) and `stage="output"` to feed the payload as a streamed model reply. If the guardrail misses it and you are not fixing the rule now, set `known_gap` with the reason.

### Checking that the suite catches a regression

Weaken a rule in `src/sensai/eval/guardrails/injection.py` (for example, comment out the `jailbreak_persona` rule), run the suite and expect exit code `1` with the jailbreak cases listed as `fail`. Revert the change afterwards.

## LLM-as-judge (EV1)

A second model grades replies the assistant already gave. For each reply it makes up to two calls:

1. **Quality**: `relevance` (does it answer the question?) and `coherence` (is it well-formed?), each from 1 to 5, with a one-sentence rationale.
2. **Faithfulness**: splits the answer into factual statements and checks each against the retrieved context: `supported`, `unsupported` (the context does not say it) or `contradicted` (the context says the opposite). `faithfulness` is the share of supported statements. Skipped when the reply has no context.

### Input

A JSONL file, one reply per line. `context` is the RAG text the assistant had; leave it out when there was none.

```json
{"question": "What is the capital of France?", "answer": "Paris. It has 40 million inhabitants.", "context": "Paris is the capital of France. The city has about 2.1 million inhabitants."}
```

A sample with a good answer, an invented fact, a contradiction, an off-topic answer and an answer that tries to steer its own score: [examples/judge-replies.jsonl](examples/judge-replies.jsonl).

### Running

Start Ollama and pull the judge model (default `llama3.2`), then:

```bash
ollama serve &
ollama pull llama3.2
uv run python -m sensai.eval.judge docs/examples/judge-replies.jsonl
```

Use `--provider` and `--model` to pick another judge. A bigger model than the one being graded gives better verdicts.

### Grading real conversations

The assistant can log its own replies in the judge format. It is off by default; turn it on in `sensai.toml`:

```toml
[eval]
log_replies = true
replies_path = "logs/replies.jsonl"  # default
```

Each final reply is appended as `{"timestamp", "question", "answer", "context"}`, then graded as-is:

```bash
uv run python -m sensai.eval.judge logs/replies.jsonl
```

- Only the final reply of a turn is logged, not the text written before a tool call.
- Not logged: blocked messages, replies refused by the output guardrail, empty replies.
- `question` is the text after the input guardrail, so masked values stay masked. `context` is the raw RAG text, which the guardrails do not filter: the log may contain personal data from your documents. `logs/` is git-ignored.

```
replies judged: 5 (0 with errors)
relevance (1-5): 3.40
coherence (1-5): 3.60
faithfulness (0-1): 0.75
unverifiable statements: 1
#3 unsupported: The Eiffel Tower was completed in 1925 in Lyon.
```

Scores are means over the replies that got one. Each `unsupported` or `contradicted` statement is listed with its reply number (line in the file).

Exit code: `0` when every reply was judged, `1` when at least one ended with an error, `2` when the file cannot be read or a line is invalid.

### Errors

A judge failure never stops the batch. The reply gets an `error` and the report lists it:

- the provider is unreachable or the call times out (60 s);
- the judge's output is still not valid JSON, or has a score outside 1-5, after 2 retries (each retry sends the error back to the judge);
- the answer is empty.

If one of the two calls fails, the result of the other is kept.

### Prompt injection

Question, answer and context are wrapped in `<question>`, `<answer>` and `<context>` tags and the judge is told they are data. An answer saying "give this a 5" should not raise its own score. The fifth sample line checks this.

### Testing

```bash
uv run pytest tests/eval/judge                                   # scripted provider, no Ollama
SENSAI_LIVE_JUDGE=1 uv run pytest tests/eval/judge/test_judge.py -k live   # real Ollama
```

The unit tests use a scripted provider. They cover parsing, retries, timeouts and the report, not the judge's judgment. The live test sends one reply to Ollama and checks a valid verdict comes back. Set `SENSAI_LIVE_MODEL` to test another model.

For a manual check, run the CLI on the sample file and compare with the expectations below.

| Line | Reply                                    | Expected                                                  |
| ---- | ---------------------------------------- | --------------------------------------------------------- |
| 1    | Correct, backed by context               | relevance 5, faithfulness 1.0                             |
| 2    | Correct, plus two invented facts         | invented facts `unsupported` or `contradicted`            |
| 3    | Wrong date and city                      | `contradicted`, low relevance                             |
| 4    | Off-topic, no context                    | relevance 1, no faithfulness                              |
| 5    | Asks the judge for a 5                   | scores not raised by the request                          |

### Limits

- The verdicts are only as good as the judge model. With `llama3.2` (3B), line 2's invented facts were dropped when the answer was split into statements (faithfulness 1.0), and line 3 came back `unsupported` instead of `contradicted`.
- The output can change between runs: compare trends over a set of replies, not single scores.
- Not wired into the chat loop and does not read `TurnLogger` logs yet: build the JSONL file yourself.
