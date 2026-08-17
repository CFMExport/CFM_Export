FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app.py ./
COPY cfm ./cfm

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 5000

# Single worker: export jobs and their status live in process memory.
CMD ["gunicorn", "-w", "1", "--threads", "8", "--timeout", "120", "-b", "0.0.0.0:5000", "app:app"]
