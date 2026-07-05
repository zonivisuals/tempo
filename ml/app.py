from workers.modal_config import app
from workers.core import storage

# Import all workers to register their functions with the Modal app
from workers.detect_scenes import detect_scenes
from workers.transcribe import transcribe
from workers.embed_visual import embed_visual
from workers.embed_text import embed_text
from workers.detect_faces import detect_faces
