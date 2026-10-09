FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock pyproject.toml README.md ./
RUN python -m pip install -r requirements.lock
COPY src ./src
RUN python -m pip install --no-deps . && useradd --uid 10001 --create-home sonar
USER 10001
ENV SONAR_BIND_HOST=0.0.0.0 SONAR_PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
CMD ["python", "-m", "sonar_web"]
