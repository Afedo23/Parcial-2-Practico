FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY tests ./tests
COPY scripts ./scripts
COPY data ./data

RUN useradd --system --uid 10001 --no-create-home app && chown -R app /app
USER app

EXPOSE 8000
# Espera a PostgreSQL, aplica migraciones y arranca gunicorn (ver src/catalogo/cli.py)
CMD ["python", "-m", "catalogo.cli", "servir"]
