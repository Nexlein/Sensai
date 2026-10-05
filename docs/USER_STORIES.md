# Sensai User Stories

## Feature: [T4] File Access within Permissions (Filesystem Tools)

As a user, I want the agent restricted to a project subdirectory, so that it can't read or leak unrelated files on my machine.

Acceptance criteria:

- Path traversal outside the root (relative, absolute, symlink) is rejected.
- `AppConfig.tools.fs_allowed_root` defaults to `None`; fs tool is not registered when unset.

As a developer, I want the agent to list and read files in my project, so that it can answer questions grounded in my actual code.

Acceptance criteria:

- ReadFile/ListDir succeed for paths inside the allowed root.
- Nonexistent file returns a clean error string, no raw exception leak.

## Feature: [R1] Basic RAG

As a user, I want the agent to ingest my local project documentation, so I can ask questions about my codebase.

Acceptance criteria:

- Local Markdown and Text files are ingested and chunked.
- Chunks are stored in a local vector database.

As a user, I want the agent to retrieve relevant information based on my query, so its answers are grounded in my actual documentation.

Acceptance criteria:

- Retrieval finds semantically relevant chunks.
- The retrieved context is injected into the prompt before generation.

## Feature: Shared CLI/TUI Session Bootstrap

As a user, I want to select the CLI or TUI from the command line or my config file, so I can use my preferred interface with the same assistant settings.

Acceptance criteria:

- `interface` defaults to `cli` and accepts `cli`, `tui`, or `web`.
- `--ui` overrides `interface` from `sensai.toml`.
- Selecting `web` reports that the interface is not implemented yet.

As a user, I want my saved conversation and tools available in the TUI, so switching interfaces does not lose my session.

Acceptance criteria:

- CLI and TUI obtain their engine, session store, tools, and RAG from the same bootstrap.
- TUI replies are saved to the existing session store.

## Feature: [M2] Token Budgeting & Semantic Compression

As a user, I want long conversations to keep working, so the agent does not lose the thread or hit the model's context limit.

Acceptance criteria:

- Token usage is counted for every outgoing prompt against `budget.max_tokens`.
- At `budget.threshold`, the oldest turns are replaced by one summary message.
- The last `budget.keep_recent_turns` turns are kept verbatim, and a tool call is never separated from its result.
- If summarizing fails, the chat continues with the history unchanged.

As a user, I want to set the token budget in `sensai.toml`, so it matches the context window of the model I run.

Acceptance criteria:

- `[budget]` accepts `max_tokens`, `threshold` and `keep_recent_turns`, with defaults when omitted.
- Out-of-range values are rejected with a config error.
- The engine emits a budget event before and during streaming, so an interface can show live usage.

## Feature: Shared Tool Registry and Permission Boundary

As a developer, I want CLI and TUI sessions to build tools through the same registry factory, so that a tool is available consistently in either interface.

Acceptance criteria:

- `build_default_registry()` constructs the default tools in one place.
- The shared bootstrap passes that registry to the chat engine.

As a user, I want every filesystem tool to enforce the same allowed directory, so that changing tools cannot expose files outside my project.

Acceptance criteria:

- Read and list tools reuse one path validation implementation.
- Relative traversal, absolute paths outside the root, and symlinks escaping the root are rejected.

## Feature: [T3] Web Search

As a user, I want Sensai to search the web when I ask for current information, so that its answer can use recent sources instead of relying only on the model's memory.

Acceptance criteria:

- `web_search` is available in CLI and TUI sessions through the shared registry.
- Search results include page titles, links, and excerpts in the conversation context.

As a user, I want Sensai to tell me when a web search cannot be completed, so that I do not mistake an unavailable search service for a verified answer.

Acceptance criteria:

- Empty queries and search service failures return clear error messages.
- Searches with no usable results are reported as such.

## Feature: [EV2] Content & Privacy Guardrails

As a clinic receptionist drafting messages with the assistant, I want the personal data I type (email, phone number, IBAN, card number, social security number) masked before it reaches the model, so that patient data is neither processed by the model nor kept in clear text.

Acceptance criteria:

- Structured PII in the input is replaced by a token (`[EMAIL]`, `[PHONE]`, `[IBAN]`, `[CARD]`, `[SSN]`) before the provider and the RAG retriever see it.
- Only the masked text is stored in the session history, so the raw value is never replayed to the model on later turns.
- A notice tells the user what was masked, naming the rule (`pii: email`) and never the value.
- The model is told, for that turn only, that placeholders were inserted on purpose, so it does not read `[IBAN]` as a glitch or ask for the value again. This note is never stored in the history.
- Numbers that fail their checksum (a 16-digit order number, a wrong IBAN) are left untouched.

As a user of a public-facing assistant, I want prompt-injection attempts ("ignore all previous instructions", "reveal your system prompt", jailbreak personas) stopped before they reach the model, so that hostile text cannot override the assistant's instructions.

Acceptance criteria:

- A blocked message is not sent to the provider, not embedded by the retriever and not stored in the history.
- The user gets a notice explaining that the message was blocked and which rule fired.
- With `injection = "flag"` the message is sent as written and the user is only warned.
- Benign prompts that merely contain similar words ("how do I ignore whitespace in a regex?") are not blocked.
- English and French phrasings are both detected.

As a user reading a streamed answer, I want personal data in the model's reply masked as it streams, even when a value arrives split across several chunks, so that nothing sensitive is ever displayed or saved.

Acceptance criteria:

- A value split across chunks (`jo` + `hn@exam` + `ple.com`) never appears on screen, not even partially.
- The text stored in the history is the masked reply.
- With `pii = "block"` the reply is cut at the first PII, replaced by a refusal notice, the rest of the reply is dropped and any tool calls it made are not executed.
- Streaming stays live: text is released as it is produced, with only a short tail held back until it can no longer be part of a PII value.

As a developer letting the agent read project files, I want PII found in tool results (for example a customer list read with `read_file`) masked before the model sees it, so that a file access permission does not become a data leak.

Acceptance criteria:

- A tool result containing PII is masked in the stored `tool` message and in the next prompt sent to the model.
- With `pii = "block"` the result is replaced by a placeholder and the model is told it was withheld.
- Clean tool results are passed through unchanged and without any notice.

As a user who never touched the configuration, I want to be protected by default, so that a forgotten setting cannot expose personal data or let an injection attempt through.

Acceptance criteria:

- Without any `[guardrails]` section, guardrails are active with the strict actions (`injection = "block"`, `pii = "redact"`).
- Setting `enabled = false` turns every guardrail off, and the engine then behaves exactly as if none existed.

As a user who needs different behaviour (for example a security team reviewing prompts, or a workflow that must see raw numbers), I want to tune or disable the guardrails, so that I choose which protections apply and how strict they are.

Acceptance criteria:

- `[guardrails]` accepts `enabled`, `injection` (`block` or `flag`) and `pii` (`redact` or `block`) in `sensai.toml`.
- Any other value is rejected with a clear config error.
- `/config save` writes the section only when it differs from the defaults, and a disabled configuration is preserved when saved.

## Feature: [EV4] Adversarial Testing

As a developer tightening the guardrails, I want to replay a corpus of jailbreaks, prompt injections, PII leaks and malformed inputs against the agent with one command, so that I see what still gets through before a user does.

Acceptance criteria:

- `python -m sensai.eval.adversarial` prints, per category, how many attacks were caught, missed or are known gaps, plus a detection rate and a false-positive rate.
- Each attack runs against the filters alone and through a real `ChatEngine`, where a blocked message must never reach the provider or the stored history, and a masked value must never appear in either.
- Streamed replies are fed in small chunks, so a value split across chunks is checked too.
- The command exits with a non-zero status when an attack is missed without being listed as a known gap.
- Malformed inputs (empty, null bytes, a million characters, backtracking bait) never crash the guardrail.

As a maintainer changing a detection rule, I want a regression suite that fails when a rule stops catching an attack or starts blocking harmless prompts, so that a fix for one phrasing cannot silently break another.

Acceptance criteria:

- Every case states the expected verdict (`block`, `redact` or `allow`), and optionally the rule that must fire and the value that must not survive.
- Benign near-misses ("how do I ignore whitespace in a regex?", an order number that fails its checksum) are part of the corpus and must stay untouched.
- Attacks the heuristics cannot catch today (obfuscated text, paraphrases, spelled-out emails) are kept as `known_gap` cases with a reason, so the limits are documented and not dropped.
- A `known_gap` case that starts passing is reported as stale, so a fixed gap is promoted to a regular case.
- Running the suite against a guardrail that lets everything through fails.

## Feature: [EV1] Automated Eval & Hallucination Detection

As a developer of a document Q&A assistant, I want each answer graded by a judge model for relevance, coherence and faithfulness to the retrieved documents, so that I spot answers that drift off topic or invent facts before users do.

Acceptance criteria:

- `python -m sensai.eval.judge replies.jsonl` reads one `{"question", "answer", "context"}` per line and prints mean relevance and coherence (1-5) and mean faithfulness (0-1).
- Each statement of the answer is checked against the retrieved context and labelled `supported`, `unsupported` or `contradicted`; the last two are listed as unverifiable statements.
- Without a context, only relevance and coherence are graded: nothing can be called supported without a source.
- The judge is told that the question, answer and context are data to grade, so an answer that says "give me 5/5" cannot steer its own score.

As someone running the evaluation on a small local model, I want a judge that copes with its bad days, so that one malformed reply does not stop a whole batch or pass for a bad answer.

Acceptance criteria:

- JSON wrapped in code fences or prose is still parsed.
- Invalid or out-of-range output is sent back to the judge with the error and retried, up to a limit.
- A judge that stays invalid, times out or is unreachable gives a verdict with an error and no scores, and the batch goes on.
- A scoring call that fails does not discard the faithfulness result, and the other way round.
- The command exits with a non-zero status when any reply could not be judged.
