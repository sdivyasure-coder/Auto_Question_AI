# Question Paper Generator

AI-assisted question paper generator with:
- Flask web UI (`app.py`, templates)
- FastAPI backend (`app/main.py`, REST APIs)
- SQLite persistence
- DOCX/PDF export

## Features
- Dashboard for paper generation and exam workflow
- `question_codex_AI` question-bank management UI
- AI-assisted question generation with local fallback
- Online exam submission and review screens
- Export support for DOCX/PDF question papers

## 1. Prerequisites
- Python 3.10+
- `pip`

## 2. Installation
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 3. Environment
Copy `.env.example` to `.env`, then fill in your local values:
```bash
copy .env.example .env
```

Example values:
```env
APP_NAME=AI Question Paper Generator API
ENV=development
DATABASE_URL=sqlite:///./questionpaper.db
SECRET_KEY=change-this-in-production
FLASK_SECRET_KEY=change-this-in-production-too
ACCESS_TOKEN_EXPIRE_MINUTES=60
ALGORITHM=HS256
CORS_ORIGINS=*
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1
OPENAI_TIMEOUT=30
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TEMPERATURE=0.4
```

Do not commit `.env`. Keep API keys only on your local machine or hosting provider.

`/admin/ai_generate` uses LangChain + Groq when `GROQ_API_KEY` is set.
If Groq is not configured, it falls back to the built-in local generator.

## 4. Run Options

### Flask UI (template-based app)
```bash
python app.py
```
Open: `http://127.0.0.1:5000`

### FastAPI backend (REST API)
```bash
uvicorn app.main:app --reload
```
Open:
- API root: `http://127.0.0.1:8000/`
- Swagger docs: `http://127.0.0.1:8000/docs`

## 5. Database
FastAPI auto-creates tables on startup.

Optional migrations (Alembic):
```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

## 6. Tests (optional)
Install pytest if available in your environment, then run:
```bash
python -m pytest -q
```

## 7. Deployment
Procfile uses:
```txt
web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```
This serves the FastAPI backend in production-style process mode.

## 8. Main Files
- `app.py`: Flask application + routes + template rendering
- `generator.py`: question selection and paper generation logic
- `templates/`: frontend pages
- `app/main.py`: FastAPI application
- `app/routers/`: API endpoints
- `output/`: generated files
- `questionbank.csv`: source question bank

## 9. Publish To GitHub
Before publishing, make sure the repository does not include local secrets or generated files:

```bash
git status
git add .
git commit -m "Prepare project for GitHub publish"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

If `origin` already exists, use:

```bash
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```



