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

## 💡 Usage Examples

Start a chat session against a local [Ollama](https://ollama.com/) instance:

```bash
sensai chat --model llama3.2
```

Type a message and press enter; the reply streams in as `sensai: ...`. Type `exit` or press
`Ctrl+C` to leave.

Options:

- `--model <name>` — model to use
- `--provider <name>` — provider to use (`ollama` by default, or `mock` for a offline demo)
- `--base-url <url>` — base URL of the provider's API (defaults to `http://localhost:11434`)
- `--config <path>` — path to a config file (defaults to `sensai.toml` in the working directory)

Instead of CLI flags, you can set defaults in a `sensai.toml` file:

```toml
provider = "ollama"
model = "llama3.2"
base_url = "http://localhost:11434"
```
