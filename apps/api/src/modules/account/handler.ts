import { Hono } from 'hono';
import { z } from 'zod';
import { createHash, randomBytes } from 'node:crypto';
import { eq } from 'drizzle-orm';
import { db } from '../../lib/db.js';
import { apiKeys } from '@tempo/db';
import { API } from '@tempo/core/constants';
import type { Variables } from '../../middleware/auth.js';
import { CreateApiKeySchema, serializeApiKey } from './schema.js';

type Env = { Variables: Variables };

const handler = new Hono<Env>();

handler.post('/api-keys', async (c) => {
  try {
    const body = await c.req.json();
    const parsed = CreateApiKeySchema.parse(body);

    const prefix = API.KEY_PREFIX;
    const secret = randomBytes(32).toString('base64url');
    const fullKey = `${prefix}${secret}`;
    const keyHash = createHash('sha256').update(fullKey).digest('hex');

    const [row] = await db
      .insert(apiKeys)
      .values({
        teamId: parsed.teamId,
        name: parsed.name,
        keyHash,
        prefix,
      })
      .returning();

    return c.json(serializeApiKey(row as any, fullKey), 201);
  } catch (err) {
    if (err instanceof z.ZodError) {
      return c.json({ error: err.errors }, 400);
    }
    return c.json({ error: 'Internal server error' }, 500);
  }
});

handler.get('/api-keys', async (c) => {
  try {
    const teamId = c.get('teamId');
    const keys = await db.select().from(apiKeys).where(eq(apiKeys.teamId, teamId));
    return c.json({
      keys: keys.map((key) => serializeApiKey(key as any)),
    });
  } catch (err) {
    return c.json({ error: 'Internal server error' }, 500);
  }
});

export default handler;
