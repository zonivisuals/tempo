import { config } from 'dotenv';
import postgres from 'postgres';
import { drizzle } from 'drizzle-orm/postgres-js';
import { createHash, randomBytes } from 'node:crypto';
import { apiKeys } from './schema/videos.js';

config({ path: '../../.env.local' });

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
  throw new Error('DATABASE_URL is required');
}

const client = postgres(DATABASE_URL);
const db = drizzle(client);

const TEAM_ID = '11111111-1111-1111-1111-111111111111';
const PREFIX = 'tmpodev_';
const secret = randomBytes(32).toString('base64url');
const fullKey = `${PREFIX}${secret}`;
const keyHash = createHash('sha256').update(fullKey).digest('hex');

await db.insert(apiKeys).values({
  teamId: TEAM_ID,
  name: 'Development Key',
  keyHash,
  prefix: PREFIX,
});

console.log('Seed complete.');
console.log(`Team ID:     ${TEAM_ID}`);
console.log(`API Key:     ${fullKey}`);
console.log(`Key Prefix:  ${PREFIX}`);

await client.end();
