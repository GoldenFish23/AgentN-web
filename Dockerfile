# Stage 1: Build the React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy the built frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Koyeb expects the app to run on port 8000
ENV PORT=8000
EXPOSE 8000

# Run with Gunicorn. Timeout is 120s to prevent LLM call failures.
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 backend.app:app