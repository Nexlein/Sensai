# Sensai

< WATASHI WA NIHONGO O SUKOSHI SHIKA HANASEMASEN />

## 📚 Documentation

- [Project Subject & Constraints](docs/SUBJECT.md)
- [Features Catalog](docs/CATALOGUE.md)

## 🚀 Getting Started for Developers

To start working on this project, clone the repository and run the setup command. This will automatically download all dependencies and install the Git hooks required to format your code!

```bash
git clone git@github.com:Nexlein/Sensai.git
cd Sensai

# Install everything automatically
make setup
```

## 🛠️ Useful Commands

- `make test` - Run the test suite
- `make lint` - Check for logical errors
- `make format` - Force format all files manually

## ✨ Features (WIP)

- Interactive CLI chat REPL streaming responses from an LLM provider
- Pluggable provider registry (currently: [Ollama](https://ollama.com/), and a `mock` provider for testing/demos)
- Config resolved from CLI args > `sensai.toml` > built-in defaults, no source changes needed to switch model/provider
- Secure filesystem tools (read/list) strictly bounded to an allowed root directory (T4 feature)
- Tool-calling engine that seamlessly orchestrates tool dispatch, handles recursion limits, and gracefully recovers from unexpected errors
- Privacy and content guardrails (EV2), on by default: prompt-injection blocking on input, PII masking or refusal on input, streamed output and tool results

## 💡 Usage Examples

Start a chat session against a local [Ollama](https://ollama.com/) instance:

```bash
sensai chat --model llama3.2
```

Type a message and press enter; the reply streams in as `sensai: ...`. Type `/exit` or press `Ctrl+C` to leave.

You can also use slash commands inside the interactive session:

- `/help` - Show available commands
- `/clear` - Clear the current conversation history
- `/new` - Start and persist a new conversation
- `/config get [key]` - View runtime configuration
- `/config set <key> <value>` - Update runtime configuration
- `/config save` - Save configuration to file

Options:

- `--ui <cli|tui>` — interface to use (defaults to `cli`)
- `--model <name>` — model to use
- `--provider <name>` — provider to use (`ollama` by default, or `mock` for a offline demo)
- `--base-url <url>` — base URL of the provider's API (defaults to `http://localhost:11434`)
- `--config <path>` — path to a config file (defaults to `sensai.toml` in the working directory)

Instead of CLI flags, you can set defaults in a `sensai.toml` file:

```toml
interface = "cli"
provider = "ollama"
model = "llama3.2"
base_url = "http://localhost:11434"
```

Run `sensai chat --ui tui` to use the Textual interface. The flag takes precedence over `interface` in `sensai.toml`. The web interface is planned but not available yet.

### Ask questions about local documents (RAG)

Start Ollama with an embedding model such as `nomic-embed-text`, then point Sensai
at a directory of Markdown or text files:

```bash
ollama pull nomic-embed-text
sensai chat --rag-dir ./docs --rag-model nomic-embed-text --rag-db rag.db
```

Sensai indexes the directory when chat starts, replacing stale chunks in the local
SQLite index. Each question retrieves the closest chunks and includes them in
the model prompt. The retrieved text is not saved in conversation history.
`--rag-dir` is optional; omit it to chat without document retrieval.

### Privacy and content guardrails

Guardrails are on by default, with no configuration needed. Tune or disable them in `sensai.toml`:

```toml
[guardrails]
enabled = true      # set to false to turn all guardrails off
injection = "block" # or "flag": warn but send the message anyway
pii = "redact"      # or "block": refuse instead of masking
```

When enabled, Sensai checks three places:

- **Your message**: prompt-injection attempts ("ignore all previous instructions", "reveal your system prompt", jailbreak personas, in English and French) are blocked and never reach the model. Personal data is masked before the model, the document retriever and the session history see it.
- **The model's reply**: personal data is masked while the reply streams, even if a value arrives split across chunks. With `pii = "block"` the reply is cut and replaced by a refusal notice.
- **Tool results**: personal data returned by a tool such as `read_file` is masked before the model sees it.

Detected personal data: email addresses, phone numbers, IBANs, credit card numbers and French social security numbers. Card, IBAN and SSN candidates are checked against their checksum, so an ordinary long number is left alone. A notice such as `⚠ Personal data in your message was masked (pii: email).` tells you what happened, naming the rule and never the value. The model is also told, for that turn, that the placeholders were inserted on purpose, so it answers "that value was hidden" instead of sounding broken.

Because the rules favour masking over leaking, an ordinary number can occasionally be masked (a 10-digit number starting with `0` looks like a French phone number). Set `enabled = false` if that gets in the way.

Limits: names and postal addresses are not detected, the injection rules are heuristics that paraphrases can get past, and personal data inside tool-call arguments or retrieved documents is not filtered.
