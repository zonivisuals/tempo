import { createMiddleware } from 'hono/factory';
import { createHash } from 'node:crypto';
import { eq } from 'drizzle-orm';
import { db } from '../lib/db.js';
import { apiKeys } from '@tempo/db';

export type Variables = {
  teamId: string;
};

export const auth = createMiddleware<{ Variables: Variables }>(async (c, next) => {
  const path = c.req.path;
  const method = c.req.method;

  if (path === '/v1/api-keys' && method === 'POST') {
    return next();
  }

  const apiKey = c.req.header('Api-Key');
  if (!apiKey) {
    return c.json({ error: 'Missing Api-Key header' }, 401);
  }

  const keyHash = createHash('sha256').update(apiKey).digest('hex');

  let key;
  try {
    [key] = await db.select().from(apiKeys).where(eq(apiKeys.keyHash, keyHash));
  } catch {
    return c.json({ error: 'Internal server error' }, 500);
  }

  if (!key) {
    return c.json({ error: 'Invalid API key' }, 401);
  }

  db.update(apiKeys)
    .set({ lastUsedAt: new Date() })
    .where(eq(apiKeys.id, key.id))
    .catch(() => {});

  c.set('teamId', key.teamId);
  await next();
});
