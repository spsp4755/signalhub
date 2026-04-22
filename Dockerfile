# Load base image in offline environment:
#   podman load -i python-3.13-slim.tar
#   podman tag docker.io/library/python:3.13-slim docker.io/library/python:3.13-slim
FROM docker.io/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INDEX=1 \
    PIP_FIND_LINKS=/app/wheels \
    PIP_ROOT_USER_ACTION=ignore \
    TZ=Asia/Seoul

WORKDIR /app

# Install all dependencies from local wheels (offline)
COPY requirements.txt ./
COPY wheels/ ./wheels/
RUN python -m pip install --only-binary=:all: -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8765

ENV DB_PATH=/app/data/analysis.db

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
