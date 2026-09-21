# Sensai - Features Catalog

This document describes the available features for the Sensai project. You must select features from this list to build upon the mandatory Base Loop.

_A group that chooses fewer well-integrated, well-justified features will be evaluated more favorably than a group that accumulates features without depth._

---

## 🛠️ Base — Mandatory for all groups

### `[B1]` Functional CLI chatbot (👍)

The common starting point. A command-line chatbot connected to a local model via Ollama, with response streaming and conversation history management within a session.

- **Real-world examples:** Claude CLI, LM Studio terminal interfaces, local chat scripts.

---

## 🧠 Memory & Context

### `[M1]` Session Persistence & Profiles (⭐)

Save and reload the messages history across distinct sessions, plus a persistent user profile (preferences, custom instructions) auto-injected at init.

- **Examples:** ChatGPT's "custom instructions", a medical assistant remembering allergies.

### `[M2]` Token Budgeting & Semantic Compression (⭐⭐ + Depends on metrics)

Count token consumption per turn against a set budget. As you approach the cap, trigger a sliding-window summarization pass that condenses the oldest turns into a compact block.

- **Examples:** Claude Projects summarizing older exchanges, customer support AI condensing long tickets.

### `[M3]` External Structured Memory (⭐⭐)

Move memory from flat files to a real database (SQLite/NoSQL). The agent reads, writes, and updates structured records (facts, entities, relationships) through CRUD operations across sessions.

- **Examples:** CRM AI updating client records, Second Brain architectures.

### `[M4]` Artifact & State Document (⭐⭐)

The agent maintains a separate living document that it updates incrementally across turns, distinct from the raw chat history. Must update the right section without rewriting or corrupting the whole document.

- **Examples:** Claude Artifacts, Cursor codebase summary, writing assistant building an article.

---

## 🔧 Tools

### `[T1]` MCP (⭐⭐⭐)

The model decides mid-generation to call an external function instead of answering. It emits a structured request, your code executes it, returns the result, and the model continues. _Tested with both your own and a preexisting MCP tool._

- **Examples:** Claude using a calculator, booking agent calling a calendar API.

### `[T2]` Sandboxed Code Execution (⭐⭐⭐)

Give the agent a sandboxed runtime (Docker or isolated subprocess) where it runs code it generated, captures stdout and tracebacks, and feeds them back to fix its own errors.

- **Examples:** ChatGPT Code Interpreter, Devin autonomous loops.

### `[T3]` Web Search (⭐⭐)

Let the agent run a live web query, parse the results, and inject them into context.

- **Examples:** Perplexity AI, ChatGPT Search.

### `[T4]` File Access within Permissions (⭐)

Filesystem operations + A permission layer defining which files/directories the agent may read or touch.

- **Examples:** Code review agent restricted to `/src`, Claude Cowork requesting explicit permissions.

### `[T5]` Structured Output (⭐)

Force the model to output valid JSON conforming to a defined schema, instead of free-form prose.

- **Examples:** OpenAI's Structured Outputs API.

---

## 📚 RAG (Retrieval-Augmented Generation)

### `[R1]` Basic RAG (⭐⭐)

Full pipeline: ingest local documents, chunk them, generate embeddings, store in a local vector store, retrieve by semantic similarity, and inject the top chunks into context.

- **Examples:** Legal assistant answering from a contract database, Google NotebookLM.

### `[R2]` Advanced RAG (⭐⭐⭐)

Extends R1 with reranking of retrieved chunks, metadata filtering, and per-chunk relevance scoring to drop near-misses.

- **Examples:** Enterprise search filtering by date/author, AI combining vector retrieval and semantic reranking.

---

## 🤖 Orchestration & Reasoning

### `[A1]` Reasoning Loops (ReAct) (⭐⭐⭐)

A family of loops that make the model's thinking explicit and iterative. Central to agentic understanding.

- **Examples:** Claude's o1/o3 "thinking" mode, Anthropic's Constitutional AI, code generators that verify output before proposing.

### `[A2]` Multi-Agent Orchestration (⭐⭐⭐)

Several specialized agents coordinate on a task, passing work between them.

- **Examples:** Support system routing tech questions to an expert and billing to a commercial agent, CrewAI (researcher + writer + critic).

### `[A3]` Human-in-the-Loop (⭐)

Before executing a critical or irreversible action, the agent suspends, presents its plan, and waits for explicit user confirmation.

- **Examples:** Claude Cowork asking for confirmation before modifying system files, Automated trading agents.

### `[A4]` Prompt Versioning (⭐)

Treat prompts as versioned artifacts (timestamped, comparable, rollback-able). Measure differences in quality or latency.

- **Examples:** PromptLayer, Langfuse.

### `[A5]` Persona (⭐)

Configurable name, tone, role, and scope without modifying code. System dynamically switches agent profiles at runtime without clearing conversation history.

- **Examples:** Educational platform with one agent per subject.

### `[A6]` Semantic Cache (⭐⭐)

Cache responses and serve them directly for semantically similar queries (matched via embeddings), skipping the model entirely.

- **Examples:** GPTCache, Redis AI semantic cache.

### `[A7]` Automated Prompt Optimization (⭐)

Build prompts dynamically from context (auto-selected few-shot examples, adaptive reformulation).

- **Examples:** Stanford's DSPy dynamically optimizing pipelines.

---

## ⚖️ Evaluation

### `[EV1]` Automated Eval & Hallucination Detection (⭐⭐⭐)

System automatically evaluates response quality (relevance, coherence, source faithfulness). An LLM acts as judge. Unverifiable statements are flagged.

- **Examples:** RAGAS for evaluating RAG pipelines, Princeton's FActScore.

### `[EV2]` Content & Privacy Guardrails (⭐⭐⭐)

Interceptors on input and output. Block unsafe prompts (input) and anonymize/refuse PII (output).

- **Examples:** OpenAI Moderation API, Nvidia NeMo Guardrails, Medical assistant anonymizing data.

### `[EV3]` Logging & Monitoring Dashboard (⭐⭐)

Structured logging of every interaction feeding a simple metrics view (latency, token counts, error rate).

- **Examples:** Langfuse, LangSmith, Helicone.

### `[EV4]` Adversarial Testing (⭐⭐)

A test suite that attacks your own agent (jailbreak attempts, prompt injections, malformed inputs).

- **Examples:** Anthropic/OpenAI red teams, AdvBench.

---

## 🖥️ UX & Lifecycle

### `[X1]` Web UI (⭐)

A decoupled web frontend over the CLI backend (streaming display, basic switching) without changing backend logic.

### `[X2]` Branching — Resume & Interrupt (⭐⭐)

- **Resume:** edit a past message and fork an alternative branch.
- **Interrupt:** abort a generation mid-stream and redirect it.
- **Examples:** ChatGPT "Edit message" button.

### `[X3]` Export & Publication (⭐)

Export history/artifacts to JSON, Markdown, PDF, and generate a public no-auth link.

- **Examples:** ChatGPT "Share conversation".

### `[X4]` Questions & Forms (⭐)

Add a way for users to answer questions asked by your LLM in a seamless way.

### `[X5]` Scheduling (⭐)

Execute tasks at defined intervals without manual intervention (daily summaries, continuous monitoring).

- **Examples:** Monitoring agent sending a news summary every morning.
