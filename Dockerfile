FROM registry.access.redhat.com/ubi9/python-312

# Add application sources with correct permissions for OpenShift
USER 0
ADD . .
RUN chown -R 1001:0 ./
USER 1001

RUN pip install -U pip setuptools pipenv && \
    pipenv install --system --deploy

ENTRYPOINT ["python", "summarizer.py"]
