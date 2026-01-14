# Premove Backend

A production-ready workflow engine backend for Android applications, providing AI-powered web automation capabilities using LLM-driven browser agents.

## 🚀 Features

- 🤖 **AI-Powered Web Automation**: Uses LLM agents (GPT-4, Claude) to intelligently navigate websites and extract data
- 🔄 **Smart Caching**: Records automation steps for efficient replay - run once, replay many times
- 📱 **Android-Ready**: CORS-enabled REST API designed for seamless mobile app integration
- ⚡ **Async Task Processing**: Celery-based distributed job queue for background processing
- 🔍 **Comprehensive Logging**: Structured logging with file rotation for debugging and monitoring
- 🛡️ **Robust Error Handling**: Custom exception hierarchy with automatic retries and graceful failures
- 💾 **Production Database**: PostgreSQL with connection pooling and optimized queries
- 📊 **Health Monitoring**: Built-in health check endpoints for service monitoring

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

**Tech Stack:**
- **FastAPI**: Modern async web framework with automatic API documentation
- **PostgreSQL**: Relational database for jobs and automation storage
- **Redis**: Message broker for Celery task queue
- **Celery**: Distributed task queue for background job processing
- **Playwright**: Headless browser automation
- **Browser-use**: LLM-powered browser agent framework
- **SQLAlchemy**: Python SQL toolkit and ORM

## 📋 Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Redis 6+
- Node.js (for Playwright browsers)

## 🔧 Installation

### 1. Clone the Repository
```bash
git clone https://github.com/RamChhabra21/premove-backend.git
cd premove-backend
```

### 2. Set Up Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Install Playwright Browsers
```bash
playwright install
```

### 5. Configure Environment Variables
```bash
cp .env.example .env
# Edit .env with your configuration
```

**Required Environment Variables:**
```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/premove_db

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# LLM API Keys
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Environment
ENVIRONMENT=development
DEBUG=True

# CORS (for Android app)
CORS_ORIGINS=*
```

### 6. Initialize Database
The application automatically creates tables on startup, or run manually:
```bash
python -c "from app.core.database import create_tables; create_tables()"
```

## 🚀 Running the Application

### Development Mode

**Terminal 1: Start the API Server**
```bash
uvicorn app.main:app --reload --port 8000
```

**Terminal 2: Start the Celery Worker**
```bash
celery -A app.celery_app worker --loglevel=info --pool=solo
```

**Terminal 3 (Optional): Start Redis**
```bash
redis-server
```

### Production Mode

```bash
# API Server (with multiple workers)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Celery Worker (with concurrency)
celery -A app.celery_app worker --loglevel=info --concurrency=4

# Optional: Celery Flower for monitoring
pip install flower
celery -A app.celery_app flower
# Visit http://localhost:5555
```

## 📚 API Documentation

Once the server is running, access interactive API documentation:
- **Swagger UI**: http://localhost:8000/docs (development only)
- **ReDoc**: http://localhost:8000/redoc (development only)

### Key Endpoints

#### Health Check
```bash
GET /health

Response:
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "development",
  "database": "connected",
  "redis": "connected"
}
```

#### Create Job
```bash
POST /api/job
Content-Type: application/json

{
  "workflow_id": "123e4567-e89b-12d3-a456-426614174000",
  "node_id": "1",
  "goal": "Find the price of iPhone 15 on Amazon",
  "workflow_type": "WEB"
}

Response:
{
  "job_id": "019bbc38-3cb0-7eef-9e0c-10f2294eecf5",
  "status": "queued"
}
```

#### Get Job Status
```bash
GET /api/job/{job_id}

Response:
{
  "id": "019bbc38-3cb0-7eef-9e0c-10f2294eecf5",
  "workflow_id": "123e4567-e89b-12d3-a456-426614174000",
  "node_id": "1",
  "goal": "Find the price of iPhone 15 on Amazon",
  "workflow_type": "WEB",
  "status": "COMPLETED",
  "result": "iPhone 15 price: $799",
  "error_message": null,
  "created_at": "2026-01-14T11:16:01Z",
  "started_at": "2026-01-14T11:16:03Z",
  "finished_at": "2026-01-14T11:16:16Z"
}
```

#### Create Web Automation
```bash
POST /api/web_automations/
Content-Type: application/json

{
  "workflow_id": "123e4567-e89b-12d3-a456-426614174000",
  "node_id": 1,
  "goal": "Extract product price from Amazon",
  "actions": {}
}
```

## 📁 Project Structure

```
premove-backend/
├── app/
│   ├── api/                    # API layer
│   │   ├── api.py             # Main API router
│   │   └── endpoints/         # Route handlers
│   │       ├── jobs.py        # Job endpoints
│   │       └── web_automations.py
│   ├── core/                   # Core functionality
│   │   ├── config.py          # Configuration management
│   │   ├── database.py        # Database setup
│   │   ├── deps.py            # Dependency injection
│   │   ├── exceptions.py      # Custom exceptions
│   │   └── logging_config.py  # Logging configuration
│   ├── jobs/                   # Job management
│   │   ├── crud.py            # Database operations
│   │   └── schemas.py         # Pydantic models
│   ├── llm/                    # LLM integration
│   │   ├── client.py          # LLM client
│   │   ├── llm_gateway.py     # LLM gateway
│   │   ├── types.py           # Type definitions
│   │   └── providers/         # LLM providers (OpenAI, Anthropic)
│   ├── models/                 # SQLAlchemy models
│   │   ├── jobs.py            # Job model
│   │   └── web_automations.py # Web automation model
│   ├── tasks/                  # Celery tasks
│   │   └── tasks.py           # Task definitions
│   ├── web/                    # Web automation
│   │   ├── executor.py        # Browser task execution
│   │   ├── service.py         # Business logic
│   │   ├── crud.py            # Database operations
│   │   ├── schemas.py         # Pydantic models
│   │   └── replay/            # Action replay engine
│   ├── utils/                  # Utilities
│   │   └── constants.py       # Constants
│   ├── celery_app.py          # Celery configuration
│   ├── main.py                # FastAPI application
│   └── redis_client.py        # Redis client
├── logs/                       # Application logs
│   ├── app.log                # All logs
│   └── error.log              # Error logs only
├── .env                        # Environment variables (gitignored)
├── .env.example               # Environment template
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## 🔐 Configuration

All configuration is managed through environment variables. See `.env.example` for all available options.

### Key Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | OpenAI API key for LLM | Required for web automation |
| `CELERY_TASK_TIME_LIMIT` | Task hard timeout (seconds) | `600` |
| `BROWSER_HEADLESS` | Run browser in headless mode | `True` |
| `CORS_ORIGINS` | Allowed CORS origins | `*` (dev), specific origins (prod) |
| `API_V1_PREFIX` | API route prefix | `/api` |

## 📊 Monitoring & Logging

### Logs
Logs are written to:
- `logs/app.log`: All application logs (rotated at 10MB)
- `logs/error.log`: Error logs only (rotated at 10MB)
- Console: Real-time output

Log level is controlled by the `DEBUG` environment variable.

### Health Monitoring
```bash
curl http://localhost:8000/health
```

Returns:
- Application status
- Database connectivity
- Redis connectivity
- Version information

### Celery Monitoring with Flower
```bash
pip install flower
celery -A app.celery_app flower
```
Visit http://localhost:5555 for real-time task monitoring.

## 🐛 Troubleshooting

### Common Issues

**Database connection error**
```bash
# Check PostgreSQL is running
pg_isready

# Verify DATABASE_URL in .env
echo $DATABASE_URL
```

**Celery worker not processing tasks**
```bash
# Check Redis is running
redis-cli ping

# Verify Celery worker is active
celery -A app.celery_app inspect active

# Check Celery broker connection
celery -A app.celery_app inspect stats
```

**Browser automation fails**
```bash
# Reinstall Playwright browsers
playwright install

# Verify OpenAI API key
echo $OPENAI_API_KEY
```

**CORS errors from Android app**
```bash
# Update CORS_ORIGINS in .env
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
```

## 🧪 Testing

### Run Tests
```bash
pytest tests/ -v
```

### Test Coverage
```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

### Manual Testing
```bash
# Test job creation
curl -X POST http://localhost:8000/api/job \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "123e4567-e89b-12d3-a456-426614174000",
    "node_id": "1",
    "goal": "go to fast.com and get network speed",
    "workflow_type": "WEB"
  }'
```

## 🐳 Docker Support

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🗺️ Roadmap

- [ ] Add authentication/authorization (JWT, API keys)
- [ ] Implement job cancellation endpoint
- [ ] Add webhook notifications for job completion
- [ ] Support for more workflow types (REASON, API, etc.)
- [ ] Comprehensive test suite (unit, integration, e2e)
- [ ] Performance optimizations (async SQLAlchemy, caching)
- [ ] Docker Compose for easy deployment
- [ ] CI/CD pipeline setup
- [ ] Metrics and observability (Prometheus, Grafana)

## 📞 Support

For issues, questions, or contributions:
- **GitHub Issues**: [Create an issue](https://github.com/RamChhabra21/premove-backend/issues)
- **Email**: ramchhabra21@example.com

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [Celery](https://docs.celeryq.dev/) - Distributed task queue
- [Playwright](https://playwright.dev/) - Browser automation
- [Browser-use](https://github.com/browser-use/browser-use) - LLM browser agent

---

Made with ❤️ by [Ram Chhabra](https://github.com/RamChhabra21)
