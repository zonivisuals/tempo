import { redis } from '@tempo/infra/redis';
import { ensureBucket } from '@tempo/infra/s3';
import { ensureShotsCollection } from '@tempo/infra/qdrant';

async function bootstrap(): Promise<void> {
  await ensureBucket();
  await ensureShotsCollection();
}

bootstrap()
  .then(() => {
    console.log('Infrastructure ready');

    process.on('SIGTERM', () => {
      console.log('Shutting down...');
      redis.disconnect();
      process.exit(0);
    });
  })
  .catch((err: unknown) => {
    console.error('Failed to initialize infrastructure:', err);
    process.exit(1);
  });
