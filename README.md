# Premove Backend

A production-ready workflow engine backend for Android applications, providing AI-powered web automation capabilities using LLM-driven browser agents.

## 🚀 Features

- 🤖 **AI-Powered Web Automation**: Uses LLM agents (GPT-4, Claude) to intelligently navigate websites and extract data.
- 🔄 **Smart Caching**: Records automation steps for efficient replay - run once, replay many times.
- 📱 **Android-Ready**: CORS-enabled REST API designed for seamless mobile app integration.
- ⚡ **Async Task Processing**: Celery-based distributed job queue for background processing.
- 🔍 **Comprehensive Logging**: Structured logging with file rotation for debugging and monitoring.
- 🛡️ **Robust Error Handling**: Custom exception hierarchy with automatic retries and graceful failures.

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

## 🔧 Installation

### 1. Clone & Set Up
```bash
git clone https://github.com/RamChhabra21/premove-backend.git
cd premove-backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your DATABASE_URL, REDIS_URL, and OPENAI_API_KEY
```

## 🚀 Running the Application

**Terminal 1: Start the API Server**
```bash
uvicorn app.main:app --reload --port 8000
```

**Terminal 2: Start the Celery Worker**
```bash
celery -A app.celery_app worker --loglevel=info --pool=solo
```

## 📚 API Documentation

Interactive documentation is available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

#### Create Job
```bash
POST /api/job
{
  "workflow_id": "123e4567-e89b-12d3-a456-426614174000",
  "node_id": "1",
  "goal": "Find the price of iPhone 15 on Amazon",
  "workflow_type": "WEB"
}
```

#### Get Job Status
```bash
GET /api/job/{job_id}
```

## 📁 Project Structure

- `app/api/`: Route handlers and API logic.
- `app/core/`: Configuration, database, and logging setup.
- `app/jobs/`: Job management and CRUD operations.
- `app/llm/`: LLM client and provider integration.
- `app/models/`: SQLAlchemy database models.
- `app/tasks/`: Celery background task definitions.
- `app/web/`: Browser automation executor and service logic.
- `app/prompts/`: LLM prompt templates.
