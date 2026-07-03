import { QdrantClient } from '@qdrant/js-client-rest';
import { EMBEDDING_DIMS } from '@tempo/core/constants';

const QDRANT_URL = process.env.QDRANT_URL ?? 'http://localhost:6333';

export const qdrant = new QdrantClient({ url: QDRANT_URL });

export async function ensureShotsCollection(): Promise<void> {
  try {
    const collections = await qdrant.getCollections();
    const exists = collections.collections.some((c: { name: string }) => c.name === 'shots');

    if (!exists) {
      await qdrant.createCollection('shots', {
        vectors: {
          visual: {
            size: EMBEDDING_DIMS.VISUAL,
            distance: 'Dot',
          },
          text: {
            size: EMBEDDING_DIMS.TEXT,
            distance: 'Dot',
          },
          face: {
            size: EMBEDDING_DIMS.FACE,
            distance: 'Dot',
          },
        },
      });
    }
  } catch (err) {
    console.error('Failed to ensure Qdrant shots collection:', err);
    throw err;
  }
}
