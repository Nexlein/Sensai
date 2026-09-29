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

### Local web search service

The web search tool uses a local [SearXNG](https://docs.searxng.org/) service.
Docker Compose starts the same configuration for every developer, with JSON
results enabled:

```bash
cp .env.example .env
# Generate a secret, then replace SEARXNG_SECRET in .env with its output.
openssl rand -hex 32
docker compose up -d searxng
curl 'http://127.0.0.1:8888/search?q=sensai&format=json'
uv run sensai chat
```

SearXNG is available at `http://127.0.0.1:8888` and bound to localhost.
Sensai registers `web_search` automatically and calls this local service when
its model requests a web search. Start SearXNG before using web search; stop it
with `docker compose down`. The local `.env` is ignored by Git; commit only
`.env.example` as the setup template.

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
