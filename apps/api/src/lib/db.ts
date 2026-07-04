import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import { env } from '@tempo/infra/env';
import * as schema from '@tempo/db';

const client = postgres(env.DATABASE_URL);
export const db = drizzle(client, { schema });
