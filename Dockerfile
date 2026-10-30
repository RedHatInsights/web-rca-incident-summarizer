# Build stage: install dependencies into a virtualenv (no root required)
FROM registry.access.redhat.com/hi/python:3.12-builder@sha256:617b920efed6bc406cb510550dcfb9fa6821fc0748c082b16380cf4a2d9dd991 AS build
WORKDIR /opt/app-root/src
COPY --chown=65532:0 Pipfile Pipfile.lock ./
RUN python3.12 -m venv .venv && \
    .venv/bin/pip install -U pip setuptools pipenv && \
    VIRTUAL_ENV=/opt/app-root/src/.venv .venv/bin/pipenv install --deploy

# Runtime stage: distroless, non-root, no shell
FROM registry.access.redhat.com/hi/python:3.12@sha256:7ec601c79877a81a86673a75440cf7f61ecc2753067513af5df6e11891867a6f
WORKDIR /opt/app-root/src
ENV PATH=/opt/app-root/src/.venv/bin:$PATH
COPY --from=build --chown=65532:0 /opt/app-root/src/.venv/ .venv/
COPY --chown=65532:0 summarizer.py prompt.txt ./
ENTRYPOINT ["python3", "summarizer.py"]
