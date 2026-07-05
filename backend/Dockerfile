# Reproducible image for the battery-optimiser backend, Cloud Run-ready.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

# Cloud Run injects $PORT (default 8080); bind to it. Shell form so $PORT expands.
ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
