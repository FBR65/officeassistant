# AgentOS-Backend (API) — schlankes Laufzeitabbild, keine Build-Werkzeuge.
FROM docker.io/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv==0.12.5

WORKDIR /app
RUN useradd --create-home --uid 10001 app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

USER app
EXPOSE 7777
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7777/health', timeout=4).status==200 else 1)"
CMD ["uv", "run", "--no-sync", "uvicorn", "officeassistant.api.main:app", "--host", "0.0.0.0", "--port", "7777"]
