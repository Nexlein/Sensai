# Technical Architecture Document — SENSAI

## 1. Project Overview

- **Business Scenario (Keynote)**: Brief summary of the chosen real-world use case (e.g., Autonomous Developer Assistant / Scientific Monitoring Agent).
- **Objective**: Build a modular, framework-free AI assistant interacting directly with Ollama's native HTTP API[cite: 1].

## 2. Design Principles

- **Clean Architecture & Decoupling**: Strict separation between Domain (Pydantic), Infrastructure (httpx/Ollama)[cite: 1], Core Business Logic (Engine), and User Interfaces (CLI/Web)[cite: 1, 2].
- **Stream-First & Event-Driven**: Real-time token streaming handled via typed events (`TextChunkEvent`, `ToolCallEvent`)[cite: 1].
- **No LLM Frameworks Constraint**: Custom implementation of the ReAct loop, JSON parsing, and RAG pipelines without LangChain, LlamaIndex, or Haystack[cite: 1, 2].

## 3. Execution Pipeline Diagram

```text
[User Request]
      │
      ▼
[1. Guardrails (EV2)] ──► Block / Anonymize PII
      │
      ▼
[2. Context Builder]  ──► Load System Prompt, Persona (A5), Memory (M1/M3), RAG (R1)
      │
      ▼
[3. LLM Provider]     ──► Stream HTTP Ollama (/api/chat)
      │
      ▼
[4. ReAct / Tool Loop]──► Execute Sandbox (T2) / MCP (T1) / Web Search (T3)
      │
      ▼
[5. Post-Process]     ──► Eval (EV1), Log Metrics (EV3), Artifact Update (M4)
      │
      ▼
[Response UI]         ──► Render via CLI (Rich) or Web (FastAPI SSE)
```
