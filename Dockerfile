# Build stage: install dependencies into the system Python
FROM registry.access.redhat.com/hi/python:3.12-builder@sha256:617b920efed6bc406cb510550dcfb9fa6821fc0748c082b16380cf4a2d9dd991 AS build
USER 0
WORKDIR /opt/app-root/src
COPY Pipfile Pipfile.lock ./
RUN pip install -U setuptools pipenv && \
    pipenv install --system --deploy

# Runtime stage: distroless, non-root, no shell
FROM registry.access.redhat.com/hi/python:3.12@sha256:14ce8115a8eb67f602070b85bee19e22856a760454e74afed17a23d41cc1ddc2
WORKDIR /opt/app-root/src
COPY --from=build /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=build /usr/local/lib64/python3.12/site-packages/ /usr/local/lib64/python3.12/site-packages/
COPY --chown=65532:0 summarizer.py prompt.txt ./
ENTRYPOINT ["python3", "summarizer.py"]
