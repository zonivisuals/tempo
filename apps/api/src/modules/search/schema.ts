import { z } from '@hono/zod-openapi';
import { SEARCH } from '@tempo/core/constants';

export const SearchRequestSchema = z.object({
  query: z.string().min(1).openapi({ example: 'Lewis standing near a foggy mountain' }),
  videoIds: z.array(z.string()).optional().openapi({ example: ['vid_abc123'] }),
  topK: z.number().int().min(1).max(SEARCH.MAX_TOP_K).default(SEARCH.DEFAULT_TOP_K),
  includeFaces: z.boolean().default(true),
  includeExpansion: z.boolean().default(true),
});

const SearchResultSchema = z.object({
  shotId: z.number().int(),
  videoId: z.string(),
  score: z.number().min(0).max(1),
  startTime: z.number(),
  endTime: z.number(),
  transcript: z.string(),
  entities: z.array(z.string()),
  thumbnailUrl: z.string(),
  hasFace: z.boolean(),
});

export const SearchResponseSchema = z.object({
  queryId: z.string(),
  results: z.array(SearchResultSchema),
  expandedCluster: z.array(SearchResultSchema).optional(),
  timing: z.object({
    stage1Visual: z.number(),
    stage2Face: z.number(),
    stage3Text: z.number(),
    total: z.number(),
  }),
});
