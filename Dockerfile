# Demo application for the Predictive Auto Deployment Platform.
# Build:  docker build -t demo-deploy-app .
# Run:    docker run -p 8080:8080 demo-deploy-app
# Test:   docker run --rm demo-deploy-app pytest

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Install dependencies first so this layer is cached between pushes
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code and tests (tests ship in the image so the pipeline
# can run them with `docker run <image> pytest`)
COPY pytest.ini .
COPY app ./app
COPY tests ./tests

# Build metadata, shown at /version (the platform can pass these as build args)
ARG APP_VERSION=1.0.0
ARG GIT_SHA=unknown
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA}

# Run as a non-root user
RUN useradd --create-home --uid 1001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8080'), timeout=2)"

# One worker + threads keeps Prometheus metrics in a single process
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --access-logfile - app.main:app"]
