import { env } from '@tempo/infra/env';

export interface ShotInfo {
  id: string;
  shotIndex: number;
  startTime: number;
  endTime: number;
  thumbnailKey: string;
}

export interface DetectScenesResult {
  shots: ShotInfo[];
}

function getModalUrl(functionName: string): string {
  const workspace = env.MODAL_WORKSPACE;
  if (!workspace) {
    throw new Error('MODAL_WORKSPACE environment variable must be set');
  }
  return `https://${workspace}--${env.MODAL_APP_NAME}-${functionName.replace(/_/g, '-')}.modal.run`;
}

function getAuthHeader(): string {
  const tokenId = env.MODAL_TOKEN_ID;
  const tokenSecret = env.MODAL_TOKEN_SECRET;
  if (!tokenId || !tokenSecret) {
    throw new Error('MODAL_TOKEN_ID and MODAL_TOKEN_SECRET must be set');
  }
  return `Bearer ${tokenId}:${tokenSecret}`;
}

async function callModal<T>(functionName: string, payload: unknown): Promise<T> {
  const url = getModalUrl(functionName);
  const auth = getAuthHeader();

  const response = await fetch(url, {
    method: 'POST',
    headers: { Authorization: auth, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Modal ${functionName} failed (${response.status}): ${body.slice(0, 512)}`);
  }

  return response.json() as Promise<T>;
}

export async function callModalDetectScenes(
  s3Key: string,
  videoId: string,
  teamId: string,
  threshold: number,
): Promise<DetectScenesResult> {
  return callModal<DetectScenesResult>('detect_scenes', {
    s3_key: s3Key,
    video_id: videoId,
    team_id: teamId,
    threshold,
  });
}

export async function callModalTranscribe(
  s3Key: string,
  videoId: string,
  shots: ShotInfo[],
): Promise<void> {
  await callModal('transcribe', { s3_key: s3Key, video_id: videoId, shots });
}

export async function callModalEmbedVisual(
  s3Key: string,
  videoId: string,
  shots: ShotInfo[],
): Promise<void> {
  await callModal('embed_visual', { s3_key: s3Key, video_id: videoId, shots });
}

export async function callModalEmbedText(videoId: string, shots: ShotInfo[]): Promise<void> {
  await callModal('embed_text', { video_id: videoId, shots });
}

export async function callModalDetectFaces(
  s3Key: string,
  videoId: string,
  shots: ShotInfo[],
): Promise<void> {
  await callModal('detect_faces', { s3_key: s3Key, video_id: videoId, shots });
}

export async function callModalDownloadYouTube(
  url: string,
  s3Key: string,
): Promise<{ ok: boolean; s3_key: string; title?: string; duration?: number }> {
  return callModal('download_youtube', { url, s3_key: s3Key });
}
