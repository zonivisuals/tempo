import { Hono } from 'hono';
import { auth } from './middleware/auth.js';
import { errorHandler } from './middleware/error.js';
import { rateLimit } from './middleware/rate-limit.js';
import { API } from '@tempo/core/constants';
import accountHandler from './modules/account/handler.js';

const app = new Hono();

app.get('/health', (c) => c.text('OK'));

app.onError(errorHandler);

app.use('/v1/*', auth);
app.use('/v1/videos', rateLimit(API.RATE_LIMIT_INDEX, API.RATE_LIMIT_WINDOW_MS));
app.route('/v1', accountHandler);

export default app;
