FROM pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime

ARG IMAGE_VERSION=0.1.0
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="MIG DRA GPU matrix benchmark" \
      org.opencontainers.image.description="Parametric PyTorch CUDA benchmark for MIG, DRA and Kueue experiments" \
      org.opencontainers.image.version="${IMAGE_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /opt/benchmark

RUN groupadd --gid 10001 benchmark \
    && useradd --uid 10001 --gid 10001 --create-home benchmark

COPY --chown=benchmark:benchmark benchmark.py /opt/benchmark/benchmark.py

USER benchmark

ENTRYPOINT ["python", "-u", "/opt/benchmark/benchmark.py"]
CMD []

