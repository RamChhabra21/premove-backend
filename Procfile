# Procfile
web: uvicorn app.main:app --host 0.0.0.0 --reload --port 8001
worker: celery -A app.celery_app worker --loglevel=info