import { Queue } from 'bullmq';
import { redis } from '@tempo/infra/redis';
import { QUEUE_VIDEO_INDEX } from '@tempo/core/constants';

export const videoIndexQueue = new Queue(QUEUE_VIDEO_INDEX, { connection: redis });
