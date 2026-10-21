# Reference: ElevenLabs Agents Guardrails

Research note for [EV2] Content & Privacy Guardrails (issue #36). Reference design we compare against, not a spec we must follow.

- Sources (fetched 2026-09-29):
  - [Guardrails docs](https://elevenlabs.io/docs/eleven-agents/best-practices/guardrails)
  - [Guardrails 2.0 blog post](https://elevenlabs.io/blog/guardrails)
- Caveat: pages were condensed by a summarizer, not copied verbatim. The docs mark the feature **Alpha**, so field names and behavior may change. Re-check the sources before quoting details in the keynote.

## 1. Model: three protection layers

| Layer                     | Goal                                           | Guardrail       |
| ------------------------- | ---------------------------------------------- | --------------- |
| System prompt hardening   | Keep the agent on its goal during long chats   | Focus           |
| User input validation     | Detect prompt injection / instruction override | Manipulation    |
| Agent response validation | Screen every reply against configured policies | Content, Custom |

Rationale: a well-written system prompt alone is not enough. Agents drift over long conversations and users try to manipulate them, so defenses are layered ("defense in depth").

## 2. Guardrail types

| Guardrail    | What it does                                                     | Layer         | Latency        | Cost                                  | Exit strategy |
| ------------ | ---------------------------------------------------------------- | ------------- | -------------- | ------------------------------------- | ------------- |
| Focus        | Reinforces the system prompt's objectives                        | System prompt | Minimal        | Included                              | n/a           |
| Manipulation | Detects prompt injection / override attempts                     | User input    | None           | Included                              | Terminates    |
| Content      | Screens for sensitive/unsafe categories, with tunable thresholds | Response      | Mode-dependent | Included                              | Configurable  |
| Custom       | Business policies written in natural language                    | Response      | Mode-dependent | Usage-based (LLM call per evaluation) | Configurable  |

A custom guardrail is evaluated by a lightweight model, independently and in parallel with generation, and returns allow/block.

### Custom guardrail fields

- **Name**: descriptive label.
- **Prompt**: natural-language blocking criteria.
- **Execution mode**: `streaming` or `blocking`.
- **Trigger action**: `end_call` or `retry`.
- **Retry feedback**: system guidance injected on retry, with placeholders `{{trigger_reason}}` and `{{agent_message}}`.

## 3. Execution modes (speed vs strictness)

| Mode      | Behavior                                   | Trade-off                                                                                     | Recommended for |
| --------- | ------------------------------------------ | --------------------------------------------------------------------------------------------- | --------------- |
| Streaming | Response starts before evaluation finishes | Near-zero delay, but a small part (often < 500 ms of audio) can reach the user before a block | Voice (default) |
| Blocking  | Response held until guardrails clear it    | +200-500 ms latency, nothing reaches the user unchecked                                       | Text            |

## 4. Exit strategies (what happens on a trigger)

- `end_call` (default): terminate the session immediately.
- `retry` (blocking mode only): regenerate up to 3 times with corrective feedback injected; end the call if violations persist.
- Blog also mentions transfer to another agent and escalation to a human.

## 5. Other features

- Per-guardrail enable/disable, configurable per agent.
- Every trigger is logged in conversation analytics.
- Conversation history redaction: sensitive entities removed from transcripts, recordings and webhooks, analytics preserved (enterprise only).

## 6. Best practices from the docs

- Combine system prompt hardening with the Focus guardrail.
- Test normal flows, edge cases and adversarial prompts.
- Blocking for text agents, streaming for voice agents.
- Put critical rules in both the system prompt and an independent custom guardrail.
- Monitor logs for false positives and tune.

## 7. Mapping to Sensai

| ElevenLabs idea                        | Sensai stance                                                                                                                           |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Named guardrail types, each toggleable | **Adopt**: independent rules enabled/disabled in `sensai.toml`                                                                          |
| Configurable action per trigger        | **Adopt**: verdict per rule (allow / redact / block / flag)                                                                             |
| Streaming vs blocking mode             | **Adopt** the trade-off. We are text-only, so blocking (or a sliding window for PII) fits                                               |
| Retry with injected feedback           | **Later**: possible for output blocks, needs a loop cap                                                                                 |
| LLM-judged custom guardrails           | **Defer**: adds a model call per turn on a small local model and is hard to unit test. Keep the rule interface open so one can be added |
| Trigger logging                        | **Adopt**: fits the existing `TurnLogger` (EV3)                                                                                         |
| History redaction                      | **Adopt**: what we store and replay must be the redacted text                                                                           |
| PII detection                          | Not covered by the docs. Ours: deterministic regex + validators (Luhn, IBAN mod-97)                                                     |
