FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 ragforge
COPY backend /app/backend
COPY samples /app/samples
RUN mkdir -p /app/data/uploads && chown -R ragforge:ragforge /app
USER ragforge
ENV PYTHONPATH=/app/backend
EXPOSE 8000
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
