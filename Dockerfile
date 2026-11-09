# ==========================================
# ETAPA 1: Construção do frontend
# ==========================================
FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci

COPY . .

RUN npm run build


# ==========================================
# ETAPA 2: Aplicação final
# ==========================================
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend

COPY --from=frontend-build /app/dist/public ./dist/public

EXPOSE 8080

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
