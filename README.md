# Premove Backend

A production-ready workflow engine backend for Android applications, providing AI-powered web automation capabilities using LLM-driven browser agents.

## 🚀 Features

- 🤖 **AI-Powered Web Automation**: Uses LLM agents (GPT-4, Claude, etc.) to intelligently navigate websites and extract data.
- 🔄 **Smart Caching**: Records automation steps for efficient replay - run once, replay many times.
- 📱 **Android-Ready**: CORS-enabled REST API designed for seamless mobile app integration.
- ⚡ **Async Task Processing**: Celery-based distributed job queue for background processing.
- 🔍 **Comprehensive Logging**: Structured logging with file rotation for debugging and monitoring.
- 🛡️ **Robust Error Handling**: Custom exception hierarchy with automatic retries and graceful failures.
- 🐳 **Dockerized**: Easy local setup and deployment using Docker and Docker Compose.

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Android   │─────▶│   FastAPI    │─────▶│  PostgreSQL │
│     App     │      │   REST API   │      │  Database   │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
                            ▼
                     ┌──────────────┐      ┌─────────────┐
                     │    Redis     │◀────▶│   Celery    │
                     │   Message    │      │   Worker    │
                     │    Broker    │      └─────────────┘
                     └──────────────┘             │
                                                    ▼
                                           ┌─────────────────┐
                                           │  Browser Agent  │
                                           │  (Playwright +  │
                                           │   LLM Agent)    │
                                           └─────────────────┘
```

## 📋 Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Redis 6+
- Node.js (for Playwright browsers)
- Docker & Docker Compose (optional, for containerized setup)

## 🔧 Installation & Setup

### 1. Clone & Set Up
```bash
git clone https://github.com/RamChhabra21/premove-backend.git
cd premove-backend
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env and fill in your DATABASE_URL, REDIS_URL, and LLM API keys.
```

## 🚀 Running the Application

### Option A: Using Docker Compose (Recommended)
This starts the API, Celery Worker, Redis, and Redis Commander (UI for Redis).
```bash
docker-compose up --build
```
- **API**: http://localhost:8001
- **Redis Commander**: http://localhost:8081

### Option B: Local Manual Setup
**1. Install Dependencies**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install
```

**2. Start the API Server**
```bash
uvicorn app.main:app --reload --port 8001
```

**3. Start the Celery Worker**
```bash
celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo
```

## 🌐 Environment Variables

| Variable | Description | Default / Example |
|----------|-------------|-------------------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@localhost:5432/db` |
| `REDIS_URL` | Redis URL for caching/state | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Redis URL for Celery broker | `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | OpenAI API Key (for GPT models) | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API Key (for Claude) | `sk-ant-...` |
| `GROQ_API_KEY` | Groq API Key | `gsk-...` |
| `BROWSER_USE_MODEL` | LLM model for browser agent | `gpt-4o` |
| `ENVIRONMENT` | Deployment environment | `development` / `production` |

## 📚 API Documentation

Interactive documentation is available at:
- **Swagger UI**: http://localhost:8001/docs (only in Debug mode)
- **ReDoc**: http://localhost:8001/redoc

### Key Endpoints

#### Health Check
`GET /health` - Returns the status of the API and its dependencies (DB, Redis).

#### Jobs
- `POST /api/v1/job` - Create a new background job.
- `GET /api/v1/job/{job_id}` - Get status and results of a job.

#### Web Automations
- `POST /api/v1/web_automations/` - Create a new web automation record.
- `GET /api/v1/web_automations/{automation_id}` - Retrieve a specific automation.

## 📁 Project Structure

- `app/api/`: Route handlers and API logic.
- `app/core/`: Configuration, database, and logging setup.
- `app/jobs/`: Job management and CRUD operations.
- `app/llm/`: LLM client and provider integration.
- `app/models/`: SQLAlchemy database models.
- `app/tasks/`: Celery background task definitions.
- `app/web/`: Browser automation executor and service logic.
- `app/prompts/`: LLM prompt templates.
- `app/utils/`: Utility functions and constants.
