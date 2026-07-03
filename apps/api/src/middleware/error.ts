import type { ErrorHandler } from 'hono';
import { ZodError } from 'zod';

export const errorHandler: ErrorHandler = (err, c) => {
  if (err instanceof ZodError) {
    return c.json(
      {
        error: 'Validation failed',
        details: err.errors,
      },
      422,
    );
  }

  console.error('Unhandled error:', err);
  return c.json({ error: 'Internal server error' }, 500);
};
