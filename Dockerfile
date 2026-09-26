FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src ./src
COPY public ./public
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir .
RUN useradd -m app && chown -R app /app
USER app
CMD ["uvicorn", "astrotarget.api:app", "--host", "0.0.0.0", "--port", "8000"]
