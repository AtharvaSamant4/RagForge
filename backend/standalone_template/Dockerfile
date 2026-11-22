FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/app
COPY requirements.lock.txt .
RUN --mount=type=secret,id=pip_config,target=/etc/pip.conf pip install --no-cache-dir -r requirements.lock.txt && useradd --create-home --uid 10001 standalone
COPY app ./app
COPY config ./config
COPY data ./data
COPY scripts ./scripts
COPY tests ./tests
RUN mkdir -p /runtime/uploads /runtime/models && chown -R standalone:standalone /runtime /srv/app
USER standalone
EXPOSE 8000
CMD ["sh", "-c", "python -m app.initialize && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
