# Oberfläche (NiceGUI + KoliBri). KoliBri-Assets entstehen beim Bau aus npm und werden
# lokal ausgeliefert; im Betrieb gibt es keinen CDN-Zugriff.

FROM docker.io/library/node:22-slim AS kolibri
WORKDIR /assets
COPY assets/package.json ./
RUN npm install --omit=dev --no-audit --no-fund
RUN mkdir -p /out && \
    cp -r /assets/node_modules/@public-ui/components/dist /out/components && \
    cp /assets/node_modules/@public-ui/theme-default/dist/index.mjs /out/theme-default.mjs

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
COPY --from=kolibri /out /app/assets/kolibri

USER app
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8099/', timeout=4).status==200 else 1)"
CMD ["uv", "run", "--no-sync", "officeassistant-ui"]
