# Sensai User Stories

## Feature: [T4] File Access within Permissions (Filesystem Tools)

As a user, I want the agent restricted to a project subdirectory, so that it can't read or leak unrelated files on my machine.

Acceptance criteria:

- Path traversal outside the root (relative, absolute, symlink) is rejected.
- `AppConfig.tools.fs_allowed_root` defaults to `"."`, the directory Sensai is launched from; `fs_allowed_root = false` unregisters the fs tools.

As a developer, I want the agent to list and read files in my project, so that it can answer questions grounded in my actual code.

Acceptance criteria:

- ReadFile/ListDir succeed for paths inside the allowed root.
- Nonexistent file returns a clean error string, no raw exception leak.

As a developer, I want the agent to create or update files in my project, so that it can apply the changes it suggests instead of only describing them.

Acceptance criteria:

- `write_file` creates a new file or replaces an existing one, creating missing parent directories inside the allowed root.
- Writing to a directory, or to a path outside the root (relative, absolute, symlink), returns a clean error and changes nothing on disk.
- The tool is available as soon as Sensai starts, rooted at the launch directory, like read/list.

As a user, I want to approve every file write before it happens, so that the agent cannot silently overwrite or create files on my machine.

Acceptance criteria:

- `write_file` is flagged `requires_confirmation = True` and goes through the human-in-the-loop prompt in the CLI and TUI.
- Declining the prompt leaves the file untouched and tells the agent the write was refused.

## Feature: [T1] MCP Tool Integration

As a developer, I want to plug an existing MCP server into Sensai through `sensai.toml`, so that the assistant can use tools I did not have to write (for example GitHub issues).

Acceptance criteria:

- Each `[mcp.servers.<name>]` table (`command`, `args`, `env`, `timeout`) starts one server at launch, and its tools appear to the model as `<name>__<tool>`.
- The model can call such a tool mid-answer and use the result, like a built-in tool.
- Tested against a self-built server (`tests/tools/mcp_test_server.py`) and the official GitHub server (`tests/tools/test_mcp_live.py`, opt-in).
- Changing settings with `/config` or `/model` keeps the MCP servers in `sensai.toml` and their tools in the session.

As a user, I want to approve every MCP tool call, so that code I did not vet cannot act on my behalf unnoticed.

Acceptance criteria:

- MCP tools are `requires_confirmation = True` and go through the human-in-the-loop prompt in the CLI and TUI.
- Declining the prompt means the server is never called, and the agent is told the call was refused.

As a user, I want a broken MCP server to stay out of my way, so that a typo in one server entry does not stop me from chatting.

Acceptance criteria:

- A server that cannot start, times out or fails the handshake is skipped with a warning at launch; the other servers and the built-in tools still work.
- A server that crashes or hangs during a call returns an error string to the model instead of freezing Sensai.
- MCP server processes are stopped when Sensai exits, including after a crash of the interface.

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

## Feature: [A3] Human-in-the-Loop Tool Confirmation

As a user, I want to review a web search request before Sensai contacts the search service, so that I control when an external tool runs.

Acceptance criteria:

- CLI and TUI show the tool name and arguments and wait for my decision before `web_search` runs.
- Approval runs the requested search; refusal leaves it unexecuted and tells me it was declined.

As a developer, I want one confirmation gate for every tool marked as sensitive, so that new write, execution, or network tools do not implement their own approval flow.

Acceptance criteria:

- `BaseTool`/`Tool` expose `requires_confirmation`; the engine checks it before each tool execution.
- A flagged tool runs only after the interface callback approves it; without a callback, the engine denies it.
- Tools without the flag run without prompting.

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

## Feature: [M3] External Structured Memory

As a developer, I want Sensai to remember my coding stack, preferred test runner, and style rules across different sessions, so that I do not have to re-explain my environment every time I start a new chat.

Acceptance criteria:

- Stored user facts (e.g. `user.preferred_language`, `user.linter`) persist across sessions in the SQLite database (`sensai.db`).
- Starting a new conversation with `/new` or without `--session` still injects known facts into the prompt when `auto_inject = true`.
- Stored facts can be updated idempotently with new values.

As a user, I want the agent to autonomously record decisions, project details, and preferences during a conversation using tools, so that future answers seamlessly use those verified facts.

Acceptance criteria:

- Agent calls `remember_fact` to store facts into structured memory across turns.
- Agent calls `recall_memory` to search or retrieve facts when needed.
- `forget_fact` is marked as a sensitive tool requiring human confirmation before deleting a fact, showing a clear preview of the targeted record.

As a user, I want to inspect, update, and delete stored memories via the `/memory` slash command, so that I maintain complete transparency and control over what the assistant remembers.

Acceptance criteria:

- `/memory list` shows all saved entities and their facts.
- `/memory set <entity> <key> <value>` creates or updates a fact directly.
- `/memory delete <entity> <key>` removes a fact.
- `/memory search <query>` finds facts matching a keyword.
- `/memory clear` wipes all structured memories.

## Feature: [T2] Sandboxed Code Execution

As a user asking the assistant to compute something or check a snippet, I want it to run Python in an isolated container and read the real output, so that I get a verified answer instead of a guess, without my machine being exposed to the code.

Acceptance criteria:

- The `run_python` tool runs the code in a throwaway Docker container with no network, a read-only filesystem, no host files, no capabilities, a non-root user and capped memory, CPU and processes.
- The reply to the model carries the exit code, stdout and stderr, each truncated past 4000 characters.
- Every run asks for confirmation first, and the full code is shown above the prompt so I read what I am approving.
- A script that runs past its timeout (10 seconds by default, 60 at most) is killed together with its container.

As a user whose generated code has a bug, I want the assistant to see the traceback and fix its own script, so that I get working code without copying errors back by hand.

Acceptance criteria:

- A failing script returns a non-zero exit code and its traceback on stderr, as a normal tool result, so the model can correct the code and run it again.
- A missing Docker binary, a stopped daemon or a missing image come back as `Error: sandbox unavailable…`, never as a script failure the model would try to fix.
- Empty code, a non-numeric or non-positive timeout are rejected before any container starts.

## Feature: Session Persistence

As a user working on a task over several days, I want to resume a named conversation, so that I do not have to explain the context again each time I start Sensai.

Acceptance criteria:

- `--session <name>` loads the conversation saved under that name, or starts an empty one with that id if none exists.
- The conversation is saved to the local SQLite database after each turn, including tool calls and tool results.
- Messages come back in the order they were sent, with their roles and tool calls intact.

As a user, I want to clear or restart a conversation from inside the chat, so that I can drop a context that no longer helps without leaving Sensai.

Acceptance criteria:

- `/clear` empties the current conversation and saves the empty state.
- `/new` starts and persists a fresh conversation with its own id and reports that id.
- Neither command sends anything to the model.

## Feature: Tool-Calling Loop

As a user asking a question that needs a tool (reading a file, searching the web), I want the assistant to call the tool and answer from its result in the same turn, so that I get one grounded reply instead of having to relay results by hand.

Acceptance criteria:

- When the model replies with tool calls, the engine runs each one, stores the result in the conversation and asks the model again.
- The loop ends as soon as the model replies without tool calls, and that reply is the final answer.
- Each tool call is sent to the interface as an event while the answer streams.

As a user, I want a model that keeps calling tools to be stopped, and a refused tool to end the turn cleanly, so that Sensai never loops forever or runs something I turned down.

Acceptance criteria:

- A turn makes at most 5 model rounds (`MAX_TOOL_ROUNDS`).
- If I decline a tool call, the engine does not call the model again; it adds a message naming the tool that was not run and ends the turn.
- A tool that fails returns an error string to the model, which can correct its call or explain the failure.

## Feature: Slash Commands

As a user in a chat session, I want to manage my session with slash commands, so that I can change settings without restarting Sensai.

Acceptance criteria:

- `/help` lists every command with its description; `/exit` leaves the session.
- `/model <name>` and `/provider <name>` take effect from the next turn and report what changed.
- Missing or extra arguments print the command's usage instead of failing.
- A line that does not start with `/` is a normal message to the assistant.

As a user who found settings that work, I want to read, change and save the configuration from the chat, so that the next launch starts with them.

Acceptance criteria:

- `/config` and `/config get [key]` show the current values; `get` accepts dotted keys such as `tools.fs_allowed_root`.
- `/config set <key> <value>` changes `model`, `provider`, `base_url` or `tools.fs_allowed_root` for the running session.
- `/config save` writes the settings to `sensai.toml`.
- An unknown key is reported as such and changes nothing.

## Feature: Groq Provider (opt-in)

As a user whose machine is too slow for a local model, I want to use a hosted Groq model instead of Ollama, so that I get fast answers without running a model locally.

Acceptance criteria:

- Ollama stays the default; Groq is used only after `provider = "groq"` in `sensai.toml` or `/provider groq`.
- The API key comes from `api_key` in `sensai.toml` or the `GROQ_API_KEY` environment variable.
- Replies stream and tool calls work as with Ollama.

As a user who pastes an API key into the configuration, I want it kept out of the screen and clear errors when it is missing, so that I do not leak it or wonder why Groq does not answer.

Acceptance criteria:

- `/config` shows the key as `***`, never its value.
- Switching provider or model keeps the configured `api_key`.
- Starting or switching to Groq without a key fails with a message naming `GROQ_API_KEY` and `api_key`, and the current provider stays active.

## Feature: Provider Errors and Thinking Time

As a user on a slow CPU model, I want to see that Sensai is still working and to stop a turn that takes too long, so that I can tell a slow model from a frozen program.

Acceptance criteria:

- After a 1 second grace, the interface shows "thinking… N s" while it waits for the model, and pauses it during a confirmation prompt.
- The local Ollama provider has no read timeout, so a slow model is never cut off.
- `Ctrl+C` in the CLI and `Esc` in the TUI cancel only the current turn, not the session.
- A cancelled turn leaves no unanswered user message in the history.

As a user whose model server is down or misconfigured, I want a one-line explanation of what failed, so that I know what to fix instead of reading a traceback.

Acceptance criteria:

- Any HTTP failure or runtime error from the provider is reported as a single line that gives the reason.
- The session stays open after the error, and I can fix the setting (for example with `/provider` or `/config set base_url`) and send the message again.

## Feature: Visible Reasoning and Effort

As a user watching a multi-step answer, I want to optionally see the model's reasoning and which step it is on, so that I can follow what it does between tool calls.

Acceptance criteria:

- Thoughts and `step N/M` lines are hidden by default and shown with `[reasoning] show_thoughts = true`, in both the CLI and the TUI.
- A thought streamed in several pieces appears as one block, not one line per piece.
- With thoughts hidden, the final answer streams as it arrives.
- When the step limit (`max_steps`, 5 by default) is reached, a notice says so and the model answers without tools.

As a user who wants faster or deeper answers, I want to change the thinking effort during a session, so that I do not have to edit `sensai.toml` and restart.

Acceptance criteria:

- `/effort` opens a picker with Low, Medium, High and Off, marks the default and the current level, and keeps the level unchanged on Esc.
- `/effort high` (or `low`, `medium`, `off`) sets it from the next turn; any other value shows the usage line and changes nothing.
- `/config save` writes the effort to `sensai.toml` and the `[reasoning]` section survives later saves.
- The default effort is `low`.

## Feature: Full Write Preview

As a user confirming a file write, I want to see every changed line, so that I know exactly what will be written before I allow it.

Acceptance criteria:

- The confirmation shows all added and removed lines, however many, with their line numbers.
- Unchanged stretches are collapsed to 3 lines of context around each change, with `⋮` between changes.
- A write that changes nothing shows "No changes".

## Feature: Web UI

As a user who prefers a browser to a terminal, I want to chat with Sensai in a web page, so that I can use it without a terminal UI.

Acceptance criteria:

- `sensai chat --ui web` serves the page on `http://127.0.0.1:8000`.
- Replies appear progressively in the page while the model writes them.
- Slash commands such as `/clear` work and their result is shown in the page.
- Resuming a session with `--session` shows the earlier messages when the page loads.

As a user who lets the model run tools, I want to approve or refuse each sensitive tool call in the page and to stop a reply that takes too long, so that I stay in control as in the terminal.

Acceptance criteria:

- A sensitive tool call shows its name, arguments and preview with Yes and No buttons; the tool runs only after Yes.
- The Stop button cancels the current reply and leaves no unanswered message in the history.
- A second message sent while a reply is in progress is refused with a message, not queued.
- A failing model server shows a one-line error in the page and the page stays usable.

## Feature: Domain Persona

As a waste-collection crew leader, I want Sensai to answer as the Régie's assistant, so that I get short French answers that cite the internal document instead of generic or invented ones.

Acceptance criteria:

- With `[persona] enabled = true` and `file = "personas/collecte.md"`, the persona text is the first system message of every call to the model.
- Corpus questions are answered in French and cite the source file, for example `[securite-collecte.md]`.
- A question the documents do not cover gets "Je ne trouve pas cette information dans les documents de la régie" instead of an invented fact.
- A missing or empty persona file stops startup with a one-line error.

As a team member running the A/B benchmark, I want to switch the persona off and on during a session, so that I can compare the generic and specialised prompts on the same questions.

Acceptance criteria:

- `/persona off` sends exactly the prompt Sensai sends without a persona, from the next turn.
- `/persona on` brings it back; `/persona` alone shows the current state.
- `/config save` keeps the chosen state in `sensai.toml`.
- Without a configured persona, `/persona` says none is configured and changes nothing.

## Feature: Feature Toggles in the Config File

As a user setting up document retrieval, I want to enable RAG and tune it in `sensai.toml`, so that I do not have to repeat CLI flags at every start and can compare runs with RAG on and off.

Acceptance criteria:

- `[rag] enabled = true` with `dir = "data/collecte"` indexes and retrieves exactly like `--rag-dir data/collecte`.
- `top_k`, `chunk_size` and `chunk_overlap` from the file change how many chunks are retrieved and how documents are split.
- `--rag-dir`, `--rag-db` and `--rag-model` on the CLI override the file.
- An invalid value (`top_k = 0`, an overlap not smaller than the chunk size, `enabled = true` without `dir`) stops startup with a config error.

As a user who does not want the model to reach the web or run code, I want to switch off web search and the sandbox in `sensai.toml`, so that the model never sees those tools.

Acceptance criteria:

- `[tools] web_search = false` removes `web_search` from the tools sent to the model; `sandbox = false` does the same for `run_python`.
- Without these keys both tools stay available, as before.
- `/config save` keeps both settings.

## Feature: Loaded Model Memory

As a user running models locally, I want to see how much RAM and VRAM each loaded model uses without leaving Sensai, so that I can tell whether my machine holds the model and its context.

Acceptance criteria:

- `/ps` prints one line per loaded model, embedding model included, for example `qwen3.5:4b · 4.1 GB · 100% CPU · ctx 8192`.
- Size and CPU/GPU split match `ollama ps` for the same models.
- With no model loaded, `/ps` says so.

As a user on a provider or server that cannot report memory, I want `/ps` to explain why it shows nothing, so that the session is not broken by the command.

Acceptance criteria:

- With the Groq provider, `/ps` answers "not available for this provider".
- With Ollama unreachable or failing, `/ps` prints one readable line, never a traceback, and the session stays usable.

## Feature: Model Options

As a user tuning answers for a given model, I want to set the temperature and the context size in `sensai.toml`, so that the model gets the window and sampling I chose instead of Ollama's defaults.

Acceptance criteria:

- `[options]` accepts `temperature`, `num_ctx`, `top_p`, `seed` and `num_predict`; each one set is sent in the `options` field of `/api/chat`, and `num_ctx` shows in the `CONTEXT` column of `ollama ps`.
- Without an `[options]` section the request is unchanged.
- `budget.max_tokens` above `num_ctx - num_predict` is rejected at startup with a one-line config error.
- `temperature = 0` with `seed = 42` gives the same reply twice for the same prompt.

As a user demonstrating the effect of a setting, I want to change a model option during a session, so that I can replay the same question and compare the replies.

Acceptance criteria:

- `/config set options.temperature 1.2` applies from the next turn without restarting.
- `/config set options.<key> none` removes the option; an invalid or incoherent value is refused with a message and leaves the setting unchanged.
- `/config save` writes the `[options]` section, and it is loaded back on the next start.

## Feature: Full Prompt Log

As a developer debugging an answer, I want to see the full prompt Sensai sent to the model, so that I can tell which system notes, documents and history the model actually received.

Acceptance criteria:

- `/prompt` shows the prompt of the last model call in the CLI, TUI and web UI, one block per message with its role, its source (tools, privacy, memory, RAG, summary, history) and its estimated tokens.
- The last line gives the estimated total against the context budget.
- Before any message, `/prompt` says no prompt was sent yet.

As a team member preparing the evaluation, I want every model call written to a log file, so that I can replay and compare what the model saw across a session.

Acceptance criteria:

- With `[eval] log_prompts = true`, each model call, tool rounds and failed calls included, adds one JSON line to `logs/prompts.jsonl` with the model, options, tool names and the messages exactly as sent.
- A personal value masked by the guardrails appears only as its placeholder, such as `[EMAIL]`.
- With logging off (the default), no file is created.

## Feature: Real Token Counts and Throughput

As a user running a model on my own machine, I want to see the real token counts and speed after each reply, so that I know how fast my hardware generates and how big my prompts really are.

Acceptance criteria:

- After each reply, the CLI, TUI and web UI show one line such as `prompt 1 024 tok · reply 187 tok · 11.4 tok/s · first token 2.1 s · total 18.5 s`.
- The counts and the rate match `ollama run <model> --verbose` for the same prompt, within rounding.
- A provider that reports no counters shows no such line, never zeros or an error.

As a team member explaining the token budget, I want the gap between the estimated and the real prompt size logged, so that I can say how far our estimate is off.

Acceptance criteria:

- With `[eval] log_prompts = true`, each prompt-log line holds the real counts, the rates and `estimate_error`.
- The estimate keeps driving the budget, so behaviour does not change with a provider that sends no counters.

## Feature: Settings Saved as They Change

As a user, I want a setting I change during a chat to still be there next time, so that I do not have to remember to save or retype it.

Acceptance criteria:

- With `autosave = true` (the default), `/config set`, `/config reset`, `/model`, `/provider`, `/effort` and `/persona on|off` write the changed key to `sensai.toml` at once, and the reply says `saved to sensai.toml`.
- Comments, key order and keys Sensai does not know are kept in the file; values given by CLI flags are not written unless changed.
- A value that is invalid, or that the running session cannot use, is refused with one line and changes neither the session nor the file; a change that would make the file fail to load at the next start is not written.

As a user who experiments, I want to try settings without touching my file, so that a test run does not overwrite my real configuration.

Acceptance criteria:

- `/config set autosave false` keeps later changes in the session only; `/config` lists them as `unsaved`.
- `/config save` writes everything; `/config reset <key>` returns a setting to its default and removes it from the file.

## Feature: Self-Describing Settings

As a new user, I want to discover every setting from inside the tool, so that I can configure Sensai without reading the source code.

Acceptance criteria:

- `/config keys [prefix]` and `sensai config keys` list each setting with its type, default, whether it needs a restart, and what it does.
- `/config` shows every value grouped by section, tagged `default`, `file`, `flag` or `session`.
- `sensai config init` writes a `sensai.toml` listing every setting, commented out at its default.

As a developer scripting a setup, I want to edit the config from the shell, so that I can prepare a demo machine without opening an editor.

Acceptance criteria:

- `sensai config get|set|reset <key>` read and write one key with the same validation as in a session.
- An invalid key or value prints one line and exits with status 1.

## Feature: Readable Test Results

As a developer or a reviewer, I want to see what each test checks and whether it passed, so that the test run documents the behaviour instead of printing dots.

Acceptance criteria:

- `make test` prints every test under its file, with a title taken from its docstring or name, and ✓, ✗ or – with the reason for a skip or a failure.
- A summary gives passed, failed and skipped counts per area (`core`, `eval`, `tools`…).
- `make test-report` writes the same list as Markdown in `reports/tests.md`.

As a developer, I want the usual pytest output when I need it, so that tools and habits relying on it keep working.

Acceptance criteria:

- `-v`, `-q` or `--classic` give the standard pytest output.
- Failure tracebacks and the short summary are unchanged.

## Feature: Benchmarks

As a team member comparing French quality, I want a replayable set of identical language tasks for each model, so that differences come from the models rather than different questions.

Acceptance criteria:

- `python -m sensai.eval.bench french --models <names>` runs six fixed tasks: explanation, resident message, grammar correction, summary, professional register and missing information.
- Every task uses temperature 0, seed 42, an 8 192-token context and an output limit of 512 tokens; thinking is disabled where supported.

As a reviewer, I want the full French answers saved for manual assessment, so that the reported quality judgement can be checked against the actual text.

Acceptance criteria:

- Reports retain the model name, exact prompt, full answer and possible output-limit truncation in JSON and readable Markdown, with a checkpoint per completed model.
- The suite does not invent an automatic language score; the documented review states its rubric and limits.

As a team member comparing model responsiveness, I want the speed suite to measure the arrival of the first streamed answer text, so that the reported delay reflects what the user waits for.

Acceptance criteria:

- The speed suite times the first non-empty answer content from the HTTP request start; empty chunks and thinking chunks do not end the timer.
- Each model uses an explicit 8 192-token context, temperature 0, seed 42 and thinking off where supported.
- The report includes the median of three warm runs, Ollama's allocated VRAM, and NVIDIA's memory allocation for Ollama processes when available; unavailable driver counters are not reported as zero.

As a team member running benchmarks on a laptop, I want completed model results saved immediately, so that a later interruption does not lose the whole campaign.

Acceptance criteria:

- Each completed model has a JSON and Markdown checkpoint under the chosen output directory's `models/` folder.
- JSON checkpoints retain the cold sample and every warm sample, including streamed first-token latency and server counters.
- A later model failure leaves earlier checkpoints readable.

As a team member preparing the defense, I want to measure which models fit our machines, so that our model choice rests on numbers.

Acceptance criteria:

- `python -m sensai.eval.bench speed` reports, per installed model, load time, prefill and decode speed, time to first token, memory and CPU/GPU placement.
- `python -m sensai.eval.bench tools` scores each model on the same tool-choice cases, counting tools called for plain questions, missed tools and wrong tools.
- Results are printed and saved as Markdown and JSON under `reports/bench/`.

As a team member, I want to prove that RAG and the persona improve answers, so that the A/B claim in the keynote is backed by a replayable script.

Acceptance criteria:

- `python -m sensai.eval.bench rag` runs the same questions without RAG, with RAG and a generic prompt, and with RAG and the persona, through Sensai's own engine.
- It reports accuracy, correct refusals on unanswerable questions, source citations, latency and prompt size per condition.

As a developer, I want to know which parts of Sensai cost time, so that optimization targets what is actually slow.

Acceptance criteria:

- `python -m sensai.eval.bench perf` times start-up, guardrails, a full turn with a mock model, prompt building, sessions, memory, RAG search and config handling, without any model.
- `python -m sensai.eval.bench context` shows how window size changes speed, memory and recall, and that a prompt over Ollama's default window is cut.
