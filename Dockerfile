FROM python:3.11-slim AS build

WORKDIR /app

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY pyproject.toml .
RUN apt-get update && apt-get install -y libpq-dev gcc && \
    pip install --no-cache-dir -e ".[dev]" && \
    rm -rf /var/lib/apt/lists/*

FROM python:3.11-slim

RUN apt-get update && apt-get install -y libpq-dev ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /venv /venv
ENV PATH="/venv/bin:$PATH"

COPY src/ src/
COPY tests/ tests/

EXPOSE 8000

CMD ["uvicorn", "leRH.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
