import { z } from '@hono/zod-openapi';

export const IndexStatsSchema = z.object({
  shotCount: z.number().int(),
  totalDuration: z.number(),
  status: z.string(),
});

export const WebhookSchema = z.object({
  url: z.string().url(),
  events: z.array(z.enum(['video.ready', 'video.failed', 'index.complete'])).optional(),
});
