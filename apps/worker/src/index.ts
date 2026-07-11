import { Worker } from 'bullmq';
import { eq } from 'drizzle-orm';
import { redis } from '@tempo/infra/redis';
import { db } from './db.js';
import { videos, shots } from '@tempo/db';
import { ensureBucket, uploadFromUrl } from '@tempo/infra/s3';
import { qdrant, ensureShotsCollection } from '@tempo/infra/qdrant';
import { QUEUE_VIDEO_INDEX, INDEXING } from '@tempo/core/constants';
import {
  callModalDetectScenes,
  callModalTranscribe,
  callModalEmbedVisual,
  callModalEmbedText,
  callModalDetectFaces,
  callModalDownloadYouTube,
} from './modal.js';

const YOUTUBE_RE = /youtube\.com|youtu\.be/i;

async function bootstrap(): Promise<void> {
  await ensureBucket();
  await ensureShotsCollection();
}

function videoS3Key(teamId: string, videoId: string): string {
  return `videos/${teamId}/${videoId}/source.mp4`;
}

bootstrap()
  .then(() => {
    console.log('Infrastructure ready');

    const worker = new Worker(
      QUEUE_VIDEO_INDEX,
      async (job) => {
        const { videoId, teamId } = job.data as { videoId: string; teamId: string };
        if (!videoId || !teamId) {
          throw new Error('Invalid job data: missing videoId or teamId');
        }

        console.log(`Processing job ${job.id}: ${job.name}`, { videoId, teamId });

        const key = videoS3Key(teamId, videoId);

        try {
          // 1. Download source video to S3
          await db
            .update(videos)
            .set({ status: 'downloading', updatedAt: new Date() })
            .where(eq(videos.id, videoId));

          console.log(`Job ${job.id}: downloading to S3`);
          const [row] = await db.select({ url: videos.url }).from(videos).where(eq(videos.id, videoId));
          if (!row) {
            throw new Error(`Video ${videoId} not found`);
          }

          const isYoutube = YOUTUBE_RE.test(row.url);
          if (isYoutube) {
            console.log(`Job ${job.id}: downloading from YouTube`);
            const result = await callModalDownloadYouTube(row.url, key);
            if (result.title) {
              await db
                .update(videos)
                .set({ title: result.title, updatedAt: new Date() })
                .where(eq(videos.id, videoId));
            }
          } else {
            await uploadFromUrl(row.url, key);
          }
          console.log(`Job ${job.id}: download complete`);

          // 2. Clean up previous index data (idempotent re-indexing)
          await db
            .update(videos)
            .set({ status: 'indexing', updatedAt: new Date() })
            .where(eq(videos.id, videoId));

          console.log(`Job ${job.id}: cleaning up previous index`);
          await db.delete(shots).where(eq(shots.videoId, videoId));
          await qdrant
            .delete('shots', {
              filter: { must: [{ key: 'videoId', match: { value: videoId } as any }] },
            })
            .catch(() => {});

          // 3. Scene detection
          console.log(`Job ${job.id}: detecting scenes`);
          const { shots: detectedShots } = await callModalDetectScenes(
            key, videoId, teamId, INDEXING.SCENE_DETECT_THRESHOLD,
          );
          console.log(`Job ${job.id}: ${detectedShots.length} shots detected`);

          // 4. Transcribe, embed-visual, detect-faces in parallel
          console.log(`Job ${job.id}: transcribing, embedding visual, detecting faces`);
          await Promise.all([
            callModalTranscribe(key, videoId, detectedShots),
            callModalEmbedVisual(key, videoId, detectedShots),
            callModalDetectFaces(key, videoId, detectedShots),
          ]);

          // 5. Embed text (depends on transcripts from step 4)
          console.log(`Job ${job.id}: embedding text`);
          await callModalEmbedText(videoId, detectedShots);

          // 6. Mark as ready
          await db
            .update(videos)
            .set({ status: 'ready', updatedAt: new Date() })
            .where(eq(videos.id, videoId));

          console.log(`Job ${job.id} complete`);
        } catch (err) {
          await db
            .update(videos)
            .set({ status: 'error', error: String(err), updatedAt: new Date() })
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
