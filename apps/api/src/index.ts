import { Hono } from 'hono';
import { serve } from '@hono/node-server';

const app = new Hono();

app.get('/health', (c) => c.text('OK'));

serve(
  {
    fetch: app.fetch,
    port: 3001,
  },
  (info) => {
    console.log(`Server is running on port ${info.port}`);
  },
);

export default app;
