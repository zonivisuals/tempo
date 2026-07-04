import { Worker } from 'bullmq';
import { eq } from 'drizzle-orm';
import { redis } from '@tempo/infra/redis';
import { db } from './db.js';
import { videos } from '@tempo/db';
import { ensureBucket } from '@tempo/infra/s3';
import { ensureShotsCollection } from '@tempo/infra/qdrant';
import { QUEUE_VIDEO_INDEX } from '@tempo/core/constants';

async function bootstrap(): Promise<void> {
  await ensureBucket();
  await ensureShotsCollection();
}

bootstrap()
  .then(() => {
    console.log('Infrastructure ready');

    const worker = new Worker(
      QUEUE_VIDEO_INDEX,
      async (job) => {
        const { videoId, teamId } = job.data as { videoId: string; teamId: string };
        if (!videoId || !teamId) {
          throw new Error(`Invalid job data: missing videoId or teamId`);
        }

        console.log(`Processing job ${job.id}: ${job.name}`, { videoId, teamId });

        const now = new Date();

        try {
          await db
            .update(videos)
            .set({ status: 'indexing', updatedAt: now })
            .where(eq(videos.id, videoId));

          // Phase 3c: replace with actual indexing (scene detect, transcribe, embed, etc.)
          await db
            .update(videos)
            .set({ status: 'ready', updatedAt: now })
            .where(eq(videos.id, videoId));

          console.log(`Job ${job.id} complete`);
        } catch (err) {
          await db
            .update(videos)
            .set({ status: 'error', error: String(err), updatedAt: now })
            .where(eq(videos.id, videoId));
          throw err;
        }
      },
      { connection: redis, concurrency: 5 },
    );

    process.on('SIGTERM', async () => {
      console.log('Shutting down...');
      await worker.close();
      redis.disconnect();
      process.exit(0);
    });
  })
  .catch((err: unknown) => {
    console.error('Failed to initialize infrastructure:', err);
    process.exit(1);
  });
