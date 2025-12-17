# LLM Setup (Ollama – Local Models)

This project uses **Ollama** to run Large Language Models (LLMs) **locally**, instead of relying on cloud-based APIs (Azure/OpenAI).  
The current setup is tested with **`minicpm-v`**, a lightweight **vision + text** model.

---

## Prerequisites
- macOS / Linux (Windows via WSL supported)
- Python 3.10+
- At least **8 GB RAM** recommended for `minicpm-v`

---

## Install Ollama

### macOS / Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Verify installation:
```bash
ollama --version
```

## Pull & Run Model
Bellow command will pull and run the model 
```bash
ollama run minicpm-v
```

- ⏳ First response can be slow — this is expected while the model loads.
- Ollama will start a local server at:

## Environment Configuration
```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=minicpm-v
```