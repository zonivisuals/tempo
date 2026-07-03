import { Hono } from 'hono';
import accountHandler from './modules/account/handler.js';

const app = new Hono();

app.get('/health', (c) => c.text('OK'));
app.route('/v1', accountHandler);

export default app;
