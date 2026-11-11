FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAQ_DB_PATH=/data/plaq.db \
    PLAQ_HOST=0.0.0.0
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-core.txt requirements-quantum.txt requirements.txt ./
RUN pip install --no-cache-dir -U pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install --no-cache-dir \
    -e ./packages/contracts -e ./packages/sdk-python \
    -e ./services/control-plane -e ./services/sandbox-manager \
    -e ./services/model-gateway -e ./services/artifact-service \
    -e ./services/agent-runtime -e ./engines/quantum \
    -e ./apps/api -e ./apps/cli -e ./apps/mcp
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/healthz')"
CMD ["uvicorn", "plaq_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
