import os

import boto3
from botocore.config import Config


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
    )


def _bucket() -> str:
    return os.environ["S3_BUCKET"]


def download_file(s3_key: str, local_path: str):
    s3 = _s3_client()
    s3.download_file(_bucket(), s3_key, local_path)


def upload_bytes(s3_key: str, data: bytes):
    s3 = _s3_client()
    s3.put_object(Bucket=_bucket(), Key=s3_key, Body=data)
