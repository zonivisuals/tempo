import { z } from '@hono/zod-openapi';

export const CreateVideoSchema = z.object({
  url: z.string().url().openapi({ example: 'https://example.com/video.mp4' }),
  title: z.string().min(1).max(255).optional(),
});

export const VideoStatusEnum = z.enum(['pending', 'downloading', 'indexing', 'ready', 'failed']);

export const VideoResponseSchema = z.object({
  id: z.string().uuid(),
  teamId: z.string().uuid(),
  title: z.string(),
  url: z.string().url(),
  duration: z.number().int().nullable(),
  status: VideoStatusEnum,
  error: z.string().nullable(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const VideoListResponseSchema = z.object({
  videos: z.array(VideoResponseSchema),
  total: z.number().int(),
});

export function serializeVideo(v: Record<string, unknown>) {
  return VideoResponseSchema.parse({
    id: v.id,
    teamId: v.teamId,
    title: v.title,
    url: v.url,
    duration: v.duration ?? null,
    status: v.status,
    error: v.error ?? null,
    createdAt: v.createdAt instanceof Date ? v.createdAt.toISOString() : v.createdAt,
    updatedAt: v.updatedAt instanceof Date ? v.updatedAt.toISOString() : v.updatedAt,
  });
}
