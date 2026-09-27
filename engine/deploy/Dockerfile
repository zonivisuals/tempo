# Tempo engine image (ADR-0008). Build context: engine/ (see compose.yaml).
#
# CUDA 12.6 + cuDNN 9 runtime: CTranslate2 (faster-whisper) needs cuBLAS 12 and cuDNN 9, and
# torch/torchvision install as the matching +cu126 builds from the PyTorch index (the PyPI
# default torch 2.14 targets CUDA 13). The GPU itself comes from the Brev host through the
# NVIDIA container toolkit (compose device reservation). Tag verified on Docker Hub.
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv

ARG TORCH_INDEX=https://download.pytorch.org/whl/cu126
WORKDIR /app

# Dependency layer: rebuilt only when pyproject.toml changes (a stub package satisfies the build).
COPY pyproject.toml ./
RUN mkdir tempo_engine && touch tempo_engine/__init__.py \
    && pip install torch==2.14.0 torchvision==0.29.0 --index-url "$TORCH_INDEX" \
    && pip install ".[ml]" \
    && pip uninstall -y tempo-engine

COPY tempo_engine ./tempo_engine
RUN pip install --no-deps .

# uid 1000 = `ubuntu`, the owner of /home/ubuntu/workspace on the Brev host (the /data mount).
USER ubuntu
CMD ["python", "-m", "tempo_engine.app"]
