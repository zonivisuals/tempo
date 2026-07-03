import app from './app.js';
import { serve } from '@hono/node-server';

serve({ fetch: app.fetch, port: 3001 }, (info) => {
  console.log(`Server running on port ${info.port}`);
});
