FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock.txt /app/requirements.txt
RUN --mount=type=secret,id=pip_config,target=/etc/pip.conf pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 ragforge
COPY backend /app/backend
COPY samples /app/samples
COPY benchmarks /app/benchmarks
COPY scripts /app/scripts
RUN mkdir -p /app/data/uploads /app/data/models && chown -R ragforge:ragforge /app
USER ragforge
ENV PYTHONPATH=/app/backend
EXPOSE 8000
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
