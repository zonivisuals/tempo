from pathlib import Path

import modal

app = modal.App("tempo-ml")

secret = modal.Secret.from_name("tempo-ml")

image = modal.Image.debian_slim(python_version="3.12").apt_install(
    "ffmpeg", "libgl1", "libglib2.0-0"
).pip_install_from_requirements(
    str(Path(__file__).parent.parent / "requirements.txt")
)

# GPU config — A10G is a good balance of cost/performance for inference
gpu_config = "A10G"
