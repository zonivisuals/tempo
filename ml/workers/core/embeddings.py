import os
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models

_client = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        kwargs: dict[str, str] = {"url": os.environ["QDRANT_URL"]}
        api_key = os.environ.get("QDRANT_API_KEY")
        if api_key:
            kwargs["api_key"] = api_key
        _client = QdrantClient(**kwargs)
    return _client


COLLECTION = "shots"


def upsert_visual(shot_id: str, vector: list[float], payload: dict[str, Any]):
    _get_client().upsert(
        COLLECTION,
        points=[
            models.PointStruct(id=shot_id, vector={"visual": vector}, payload=payload)
        ],
    )


def upsert_text(shot_id: str, vector: list[float], payload: dict[str, Any]):
    _get_client().upsert(
        COLLECTION,
        points=[
            models.PointStruct(id=shot_id, vector={"text": vector}, payload=payload)
        ],
    )


def upsert_face(shot_id: str, vector: list[float], payload: dict[str, Any]):
    _get_client().upsert(
        COLLECTION,
        points=[
            models.PointStruct(id=shot_id, vector={"face": vector}, payload=payload)
        ],
    )
