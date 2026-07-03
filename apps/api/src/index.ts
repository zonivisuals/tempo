import app from './app.js';
import { serve } from '@hono/node-server';
import { ensureBucket } from '@tempo/infra/s3';
import { ensureShotsCollection } from '@tempo/infra/qdrant';

serve({ fetch: app.fetch, port: 3001 }, (info) => {
  console.log(`Server running on port ${info.port}`);

  Promise.all([
    ensureBucket().catch((err: unknown) => console.error('Failed to ensure S3 bucket:', err)),
    ensureShotsCollection().catch((err: unknown) =>
      console.error('Failed to ensure Qdrant collection:', err),
    ),
  ]);
});
