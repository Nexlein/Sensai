# Sensai documentation

## Using Sensai

| Document                             | For                                                                  |
| ------------------------------------ | -------------------------------------------------------------------- |
| [../README.md](../README.md)         | Install, first chat, features, commands                              |
| [configuration.md](configuration.md) | Every setting, `/config`, `sensai config`, autosave                  |
| [benchmarks.md](benchmarks.md)       | What is fast and what is not, model comparison, limits of the models |

## Understanding the code

| Document                           | For                                                     |
| ---------------------------------- | ------------------------------------------------------- |
| [architecture.md](architecture.md) | Layers, one turn step by step, where each feature lives |
| [code-review.md](code-review.md)   | What is good, what was fixed, what is still weak        |
| [testing.md](testing.md)           | Running and reading the tests, live tests               |

## Features in depth

| Document                                                             | Feature                                     |
| -------------------------------------------------------------------- | ------------------------------------------- |
| [features/mcp.md](features/mcp.md)                                   | MCP servers as tools (T1)                   |
| [features/sandbox.md](features/sandbox.md)                           | Python sandbox in Docker (T2)               |
| [features/memory.md](features/memory.md)                             | Structured long-term memory (M3)            |
| [features/evaluation.md](features/evaluation.md)                     | Adversarial suite (EV4) and LLM judge (EV1) |
| [features/guardrails-reference.md](features/guardrails-reference.md) | Reference design for the guardrails (EV2)   |

## Project

| Document                            | For                                                              |
| ----------------------------------- | ---------------------------------------------------------------- |
| [SUBJECT.md](SUBJECT.md)            | The assignment and its rules                                     |
| [CATALOGUE.md](CATALOGUE.md)        | Feature catalogue (ids such as T1, R1, EV2)                      |
| [USER_STORIES.md](USER_STORIES.md)  | Two or more user stories per feature                             |
| [soutenance/](soutenance/README.md) | Defense preparation, in French: scenario, demo, models, measures |

Data: [`../data/collecte/`](../data/collecte/) is the fictional corpus of the demo scenario,
[`../data/bench/`](../data/bench/) the benchmark question set.
