# Image for the Python streaming services (producer + consumer). Spark runs from the
# bitnami/spark image; see docker-compose.yml. Nothing is assumed installed on the host
# except Docker.
FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

COPY requirements.txt requirements-streaming.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt -r requirements-streaming.txt

COPY app ./app
COPY streaming ./streaming
COPY scripts ./scripts
COPY tests/fixtures ./tests/fixtures

# default: run the Bronze stream consumer (overridden per service in compose)
CMD ["python", "-m", "streaming.run_consumer"]
