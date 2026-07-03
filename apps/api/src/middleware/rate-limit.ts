import { createMiddleware } from 'hono/factory';
import type { Variables } from './auth.js';

interface RateLimitEntry {
  count: number;
  resetAt: number;
}

export function rateLimit(maxRequests: number, windowMs: number) {
  const store = new Map<string, RateLimitEntry>();

  const cleanup = setInterval(() => {
    const now = Date.now();
    for (const [key, entry] of store) {
      if (entry.resetAt <= now) {
        store.delete(key);
      }
    }
  }, 60_000);

  if (cleanup.unref) {
    cleanup.unref();
  }

  return createMiddleware<{ Variables: Variables }>(async (c, next) => {
    const teamId = c.get('teamId');
    const now = Date.now();
    const entry = store.get(teamId);

    if (!entry || entry.resetAt <= now) {
      store.set(teamId, { count: 1, resetAt: now + windowMs });
      return next();
    }

    entry.count++;

    if (entry.count > maxRequests) {
      const retryAfter = Math.ceil((entry.resetAt - now) / 1000);
      c.header('Retry-After', String(retryAfter));
      return c.json({ error: 'Rate limit exceeded. Try again later.' }, 429);
    }

    return next();
  });
}
