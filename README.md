# Question_Codex_AI

AI-assisted question paper generator with:
- Flask web UI
- FastAPI REST backend
- SQLite persistence
- DOCX/PDF export
- `question_codex_AI` question-bank management

## Project Folder
The application source code is inside:

```bash
Question_Codex_AI/
```

## Features
- Dashboard for question paper generation and exam workflow
- Question-bank management UI
- AI-assisted question generation with local fallback
- Online exam submission and review screens
- Export support for DOCX/PDF question papers

## Installation
```bash
cd Question_Codex_AI
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Environment
Copy the example environment file and fill in your local values:

```bash
copy .env.example .env
```

Keep `.env` private. Do not commit API keys or secrets.

## Run Flask UI
```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Run FastAPI Backend
```bash
uvicorn app.main:app --reload
```

Open:
- API root: `http://127.0.0.1:8000/`
- Swagger docs: `http://127.0.0.1:8000/docs`

## Tests
```bash
python -m pytest -q
```

## Main Files
- `Question_Codex_AI/app.py`: Flask application and template routes
- `Question_Codex_AI/generator.py`: question generation logic
- `Question_Codex_AI/templates/`: frontend pages
- `Question_Codex_AI/app/main.py`: FastAPI application
- `Question_Codex_AI/questionbank.csv`: question-bank source data
