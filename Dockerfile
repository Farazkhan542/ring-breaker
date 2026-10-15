FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    RB_STATE_DIR=/tmp/state RB_CACHE_DIR=/app/cache
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY ringbreaker ringbreaker
COPY web web
COPY data data
COPY results results
COPY cache cache
# Cloud Run sets PORT; single worker so the in-memory audit log and case store are shared.
CMD exec uvicorn ringbreaker.api:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
