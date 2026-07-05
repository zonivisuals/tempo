import { S3Client, HeadBucketCommand, CreateBucketCommand, PutObjectCommand } from '@aws-sdk/client-s3';
import { env } from './env.js';

export const S3_ENDPOINT = env.S3_ENDPOINT;
export const S3_REGION = env.S3_REGION;
export const S3_ACCESS_KEY_ID = env.S3_ACCESS_KEY_ID;
export const S3_SECRET_ACCESS_KEY = env.S3_SECRET_ACCESS_KEY;
export const S3_BUCKET = env.S3_BUCKET;

export const s3 = new S3Client({
  endpoint: S3_ENDPOINT,
  region: S3_REGION,
  credentials: {
    accessKeyId: S3_ACCESS_KEY_ID,
    secretAccessKey: S3_SECRET_ACCESS_KEY,
  },
  forcePathStyle: true,
});

export async function ensureBucket(): Promise<void> {
  try {
    await s3.send(new HeadBucketCommand({ Bucket: S3_BUCKET }));
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'NotFound') {
      await s3.send(new CreateBucketCommand({ Bucket: S3_BUCKET }));
      return;
    }
    throw err;
  }
}

export async function uploadFromUrl(sourceUrl: string, s3Key: string): Promise<void> {
  const response = await fetch(sourceUrl);
  if (!response.ok) {
    throw new Error(`Failed to fetch source URL: ${response.status} ${response.statusText}`);
  }
  const contentType = response.headers.get('content-type') || 'video/mp4';
  const body = await response.arrayBuffer();
  await s3.send(new PutObjectCommand({ Bucket: S3_BUCKET, Key: s3Key, Body: new Uint8Array(body), ContentType: contentType }));
}
