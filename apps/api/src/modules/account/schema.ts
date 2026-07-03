import { z } from '@hono/zod-openapi';

export const CreateApiKeySchema = z.object({
  name: z.string().min(1).max(100).openapi({ example: 'Production API Key' }),
});

export const ApiKeyResponseSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  prefix: z.string(),
  key: z.string().optional(),
  createdAt: z.string().datetime(),
  lastUsedAt: z.string().datetime().nullable(),
});

export const ApiKeyListResponseSchema = z.object({
  keys: z.array(ApiKeyResponseSchema.omit({ key: true })),
});

export function serializeApiKey(row: Record<string, unknown>, includeKey?: string) {
  return ApiKeyResponseSchema.parse({
    id: row.id,
    name: row.name,
    prefix: row.prefix,
    key: includeKey,
    createdAt: row.createdAt instanceof Date ? row.createdAt.toISOString() : row.createdAt,
    lastUsedAt: row.lastUsedAt instanceof Date ? row.lastUsedAt.toISOString() : (row.lastUsedAt ?? null),
  });
}

export function serializeApiKeyList(row: Record<string, unknown>) {
  return ApiKeyResponseSchema.omit({ key: true }).parse({
    id: row.id,
    name: row.name,
    prefix: row.prefix,
    createdAt: row.createdAt instanceof Date ? row.createdAt.toISOString() : row.createdAt,
    lastUsedAt: row.lastUsedAt instanceof Date ? row.lastUsedAt.toISOString() : (row.lastUsedAt ?? null),
  });
}
