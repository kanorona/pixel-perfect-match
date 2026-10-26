FROM node:22-bookworm-slim AS frontend-build

WORKDIR /src/frontend
COPY frontend/package.json ./
# Resolve native optional packages for this Linux image.
RUN npm install --no-package-lock
COPY frontend/ ./

# The browser calls FastAPI on the same origin as the page.
ENV BLUEPRINT_STATIC_BUILD=1 \
    VITE_SUPABASE_URL=__BLUEPRINT_SAME_ORIGIN__ \
    VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_local_demo
RUN npm run build && test -f dist/client/_shell.html

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH" \
    BLUEPRINT_DATABASE_URL=sqlite:////data/blueprint.db

WORKDIR /app/backend
RUN python -m pip install --no-cache-dir uv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/app ./app
COPY --from=frontend-build /src/frontend/dist/client ./static

RUN mkdir -p /data && useradd --create-home appuser && chown appuser:appuser /data
USER appuser

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
