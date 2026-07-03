import modal

app = modal.App("tempo-ml")

image = modal.Image.debian_slim(python_version="3.12").pip_install_from_requirements(
    "requirements.txt"
)

# GPU config — A10G is a good balance of cost/performance for inference
gpu_config = modal.gpu.A10G()
