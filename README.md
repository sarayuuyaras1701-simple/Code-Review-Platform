# 🔍 AI Code Review Platform

An intelligent code review assistant built with **Python + Streamlit**. Paste code or load a file from GitHub, and the app combines built-in static analysis with an AI review (Google Gemini or a local Ollama model) to find bugs, security problems, performance issues and code-quality problems.

---

## ✨ Features

- **Static analysis (Python):** syntax validation, counts of functions, classes, imports and comments.
- **Security scan:** flags patterns such as `eval()`, `exec()`, `os.system()`, subprocess calls, hard-coded passwords and API keys, possible SQL injection, and disabled SSL verification.
- **Code quality checks:** long lines, unresolved TODOs, very large files.
- **Code score (0-100):** a simple score based on the issues found.
- **AI senior developer review:** executive summary, bugs, security issues, performance tips, code quality, an improved version of the code, and a final assessment.
- **Two AI engines:** Google Gemini (cloud) or Ollama (local/private).
- **GitHub loader:** review a file straight from a GitHub URL.
- **Reliable Gemini calls:** automatic retries with backoff for temporary errors (503/429/5xx and dropped connections), plus optional fallback models.
- **Downloadable report** (`.txt`) and in-session review history.

Supported languages in the selector: Python, Java, C, C++, JavaScript. (Detailed static analysis is Python-only; the security/quality scans and AI review work for all of them.)

---

## 📋 Requirements

- Python 3.9 or newer
- A Gemini API key (free from [Google AI Studio](https://aistudio.google.com)) if you use Gemini
- [Ollama](https://ollama.com) with the `llama3.2` model installed if you use Ollama

Python packages:

```
streamlit
requests
python-dotenv
```

---

## 🚀 Setup

### 1. Get the project

Put `app.py` in a folder of your choice and open that folder in a terminal.

### 2. Create a virtual environment (recommended)

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install streamlit requests python-dotenv
```

### 4. Add your Gemini API key

Create a file named `.env` in the same folder as `app.py`:

```
GEMINI_API_KEY=your_real_api_key_here
```

Optional settings (also in `.env`):

```
GEMINI_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_MODELS=gemini-3.5-flash,gemini-3.1-flash-lite
```

> ⚠️ **Never commit your API key.** Add `.env` to your `.gitignore`. If your project folder syncs to a cloud service (e.g. OneDrive), keep the key in `.env`, not in the source code.

Alternatively, when deploying to Streamlit Community Cloud, put the key in the app's **Secrets** as:

```toml
GEMINI_API_KEY = "your_real_api_key_here"
```

### 5. Run the app

```bash
streamlit run app.py
```

The app opens in your browser (usually at http://localhost:8501).

---

## 🧭 How to Use

1. Choose the **Programming Language** and **AI Engine** in the sidebar.
2. Paste your code in the **Paste Code** tab, or open the **GitHub File** tab, enter a link like `https://github.com/user/repo/blob/main/app.py` and click **Load GitHub Code**.
3. Click **🚀 REVIEW CODE**.
4. Read the dashboard (score, security issues, quality issues, static analysis) and the AI review.
5. Click **Download Complete Review Report** to save the results.

If you paste code, it takes priority over any GitHub code that was loaded earlier. Use **Clear loaded GitHub code** to remove the loaded file.

---

## ⚙️ Configuration

| Setting | Where | Description |
|---|---|---|
| `GEMINI_API_KEY` | `.env` or Streamlit secrets | Your Gemini API key (required for Gemini) |
| `GEMINI_MODEL` | `.env` (or sidebar) | Main Gemini model. Default: `gemini-3.8-flash` |
| `GEMINI_FALLBACK_MODELS` | `.env` (or sidebar) | Comma-separated models to try if the main one is busy |
| Ollama model | `ollama_review()` in `app.py` | Defaults to `llama3.2` at `http://localhost:11434` |

Retry behavior is controlled by `MAX_RETRIES_PER_MODEL` and `RETRYABLE_STATUS` near the top of `app.py`.

---

## 🛠️ Troubleshooting

| Problem | Meaning | What to do |
|---|---|---|
| `400 API_KEY_INVALID` | The API key is wrong or still a placeholder | Check `GEMINI_API_KEY` in `.env`, then restart the app |
| `404 NOT_FOUND` / model not available | The model name is retired or not available to your account | Change the model in the sidebar. Check available names in Google AI Studio |
| `503 UNAVAILABLE` | Google's model is overloaded | The app retries automatically. Add fallback models in the sidebar, or wait and try again |
| `Connection aborted` / `RemoteDisconnected` | The connection to Google was cut | Turn off VPN/proxy, check antivirus or firewall, or try another network |
| Ollama connection error | Ollama is not running | Start Ollama and run `ollama pull llama3.2` |
| `Gemini API key not configured` | No key found | Add `GEMINI_API_KEY` to `.env` and restart |

Model names change over time. If a model stops working, check the current list at [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models).

---

## 📁 Project Structure

```
your-project/
├── app.py        # Main Streamlit application
├── .env          # Your API key and settings (do not commit)
└── README.md
```

---

## 🔒 Security Notes

- The API key is sent in a request header, not in the URL.
- The built-in security scan uses simple pattern matching, so it can miss issues or flag false positives. Treat it as a first pass, not a full audit.
- Code you submit is sent to Google when using Gemini. For private or sensitive code, use the Ollama option, which runs locally.
- AI reviews can be wrong. Always verify suggested fixes before using them.

---

## 🧰 Built With

- [Streamlit](https://streamlit.io)
- [Google Gemini API](https://ai.google.dev)
- [Ollama](https://ollama.com)
- Python `ast`, `re`, `requests`
-