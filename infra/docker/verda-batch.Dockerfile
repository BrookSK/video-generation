# Reuse the CUDA/Blackwell worker image from the validated pipeline.
ARG WORKER_IMAGE
FROM ${WORKER_IMAGE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*
COPY infra/docker/verda-batch-start.sh /usr/local/bin/verda-batch-start
COPY apps/worker/src/avatar_worker /app/apps/worker/src/avatar_worker
COPY docs/models /app/docs/models
COPY infra/docker/verda-batch-sitecustomize.py /opt/estudioia/blackwell/sitecustomize.py
COPY --chmod=755 infra/docker/verda-batch-avatar-python /usr/local/bin/verda-batch-avatar-python
ENV AVATAR_PYTHON=/usr/local/bin/verda-batch-avatar-python
ENV MODELS_DIR=/data/estudioia/models WORKER_KINDS=video PORT=8000
USER app
EXPOSE 8000
CMD ["/bin/sh", "/usr/local/bin/verda-batch-start"]
