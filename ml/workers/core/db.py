import os
import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def insert_shot(conn, video_id: str, shot_index: int, start_time: int, end_time: int, thumbnail_key: str) -> str:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """INSERT INTO shots (video_id, shot_index, start_time, end_time, thumbnail_key)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id""",
            (video_id, shot_index, start_time, end_time, thumbnail_key),
        )
        return str(cur.fetchone()["id"])


def update_shot_transcript(conn, shot_id: str, transcript: str, entities: list[str] | None = None):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE shots SET transcript = %s, entities = %s WHERE id = %s",
            (transcript, entities, shot_id),
        )


def set_shot_has_face(conn, shot_id: str):
    with conn.cursor() as cur:
        cur.execute("UPDATE shots SET has_face = 1 WHERE id = %s", (shot_id,))


def get_shot_transcripts(conn, video_id: str) -> list[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, shot_index, transcript, entities FROM shots WHERE video_id = %s ORDER BY shot_index",
            (video_id,),
        )
        return [dict(r) for r in cur.fetchall()]
