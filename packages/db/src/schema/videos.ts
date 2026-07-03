import { pgTable, uuid, text, integer, timestamp, varchar } from 'drizzle-orm/pg-core';

export const videos = pgTable('videos', {
  id: uuid('id').primaryKey().defaultRandom(),
  teamId: uuid('team_id').notNull(),
  title: text('title').notNull(),
  url: text('url').notNull(),
  duration: integer('duration'),
  status: varchar('status', { length: 20 }).notNull().default('pending'),
  error: text('error'),
  createdAt: timestamp('created_at').notNull().defaultNow(),
  updatedAt: timestamp('updated_at').notNull().defaultNow(),
});

export const shots = pgTable('shots', {
  id: uuid('id').primaryKey().defaultRandom(),
  videoId: uuid('video_id').notNull().references(() => videos.id, { onDelete: 'cascade' }),
  shotIndex: integer('shot_index').notNull(),
  startTime: integer('start_time').notNull(),
  endTime: integer('end_time').notNull(),
  transcript: text('transcript'),
  entities: text('entities').array(),
  clusterId: integer('cluster_id'),
  hasFace: integer('has_face').default(0),
  thumbnailKey: text('thumbnail_key'),
  createdAt: timestamp('created_at').notNull().defaultNow(),
});

export const apiKeys = pgTable('api_keys', {
  id: uuid('id').primaryKey().defaultRandom(),
  teamId: uuid('team_id').notNull(),
  name: text('name').notNull(),
  keyHash: text('key_hash').notNull(),
  prefix: varchar('prefix', { length: 8 }).notNull(),
  lastUsedAt: timestamp('last_used_at'),
  createdAt: timestamp('created_at').notNull().defaultNow(),
});
