import { Hono } from 'hono';
import { eq } from 'drizzle-orm';
import { db } from '../../lib/db.js';
import { videos } from '@tempo/db';
import type { Variables } from '../../middleware/auth.js';
import { CreateVideoSchema, serializeVideo } from './schema.js';

type Env = {
  Variables: Variables;
};
const handler = new Hono<Env>();

handler.post('/', async (c) => {
  const body = await c.req.json();
  const parsed = CreateVideoSchema.parse(body);

  const [row] = await db
    .insert(videos)
    .values({
      teamId: c.get('teamId'),
      url: parsed.url,
      title: parsed.title ?? 'Untitled',
      status: 'pending',
    })
    .returning();

  return c.json(serializeVideo(row as any), 201);
});

handler.get('/:id', async (c) => {
  const [row] = await db
    .select()
    .from(videos)
    .where(eq(videos.id, c.req.param('id')));

  if (!row || row.teamId !== c.get('teamId')) {
    return c.json({ error: 'Video Not found' }, 404);
  }

  return c.json(serializeVideo(row as any), 200);
});

handler.delete('/:id', async (c) => {
  const [row] = await db
    .delete(videos)
    .where(eq(videos.id, c.req.param('id')))
    .returning({ id: videos.id, teamId: videos.teamId });

  if (!row || row.teamId !== c.get('teamId')) {
    return c.json({ error: 'Video not found' }, 404);
  }

  return c.body(null, 204);
});

export default handler;
