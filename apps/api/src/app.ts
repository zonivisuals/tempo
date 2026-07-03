import { Hono } from 'hono';
import { auth } from './middleware/auth.js';
import accountHandler from './modules/account/handler.js';

const app = new Hono();

app.get('/health', (c) => c.text('OK'));

app.use('/v1/*', auth);
app.route('/v1', accountHandler);

export default app;
