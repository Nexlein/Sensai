# Sensai - Project Subject

> **Subtitle:** `< WATASHI WA NIHONGO O SUKOSHI SHIKA HANASEMASEN />`

## 1. Core Constraints & Technical Rules

- **Language:** Python 3.10 or higher.
- **Forbidden Frameworks:** You **MAY NOT** use any LLM frameworks (e.g., LangChain, LlamaIndex, Haystack, or equivalent).
- **Authorized Packages:** Standard libraries and utility packages (e.g., `requests`, `sqlite3`, `fastapi`) are fully allowed for non-LLM concerns.
- **Ollama API:** All calls to the language model **must** go directly through the Ollama HTTP API.

## 2. Project Goal

Build the most capable AI assistant you can, starting from a minimal local chatbot and enriching it with features of your choosing. Every significant technical decision and tradeoff must be justified as a response to real use cases (e.g., a medical assistant detecting PII, a developer agent in a sandbox, etc.).

## 3. The Base Loop (MVP)

The project **must** implement a functional CLI chatbot connected to a local Ollama model with the following baseline features:

- **Streaming responses:** Output must be rendered progressively, not as a single blocked response.
- **In-session conversation history:** The model must receive prior conversational turns as context.
- **Clean error handling:** Must gracefully handle unavailable models, empty inputs, and connection failures.
- **Model selectable:** The active model must be selectable via a CLI argument or a configuration file (without modifying the source code).

_Note: Achieving only the Base Loop will not net you any points. You must build upon this foundation._

## 4. Deliverables

Your repository must include at a minimum:

- All source code.
- A `README.md` with setup instructions, a feature list, and usage examples.
- A dependency specification (e.g., `requirements.txt`, `pyproject.toml`).
- **User Stories** for each feature implemented.

### User Story Format

For each implemented feature, write at least two user stories demonstrating real use cases:

```text
As a [type of user], I want to [action], so that [outcome].

Acceptance criteria:
- Observable behavior 1
- Observable behavior 2
- Observable behavior 3
```

_Note: User stories are the contract between technical choices and the problem solved._

## 5. Final Keynote Presentation

Your final presentation will be a keynote. Expectations:

- **Scenario-driven:** Open with a concrete scenario (who is using it, context, purpose).
- **Live Demo:** Demonstrate features live within a coherent system (no disconnected demos).
- **Technical Justification:** Explain technical choices, what was considered, and what was ruled out.
- **Honest Assessment:** Discuss what works well, current limits, and what you would do differently.
- **Fallback Plan:** Have fallback screenshots/recordings prepared in case of live system crashes or network failures.
