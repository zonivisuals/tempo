export type VideoStatus = 'pending' | 'downloading' | 'indexing' | 'ready' | 'failed';

export interface Video {
  id: string;
  teamId: string;
  title: string;
  url: string;
  duration: number;
  status: VideoStatus;
  error?: string;
  createdAt: string;
  updatedAt: string;
}

export interface Shot {
  shotId: number;
  videoId: string;
  startTime: number;
  endTime: number;
  transcript: string;
  entities: string[];
  clusterId: number;
  hasFace: boolean;
  thumbnailUrl: string;
}

export interface SearchQuery {
  query: string;
  videoIds?: string[];
  topK: number;
  includeFaces: boolean;
  includeExpansion: boolean;
}

export interface SearchResult {
  shotId: number;
  videoId: string;
  score: number;
  startTime: number;
  endTime: number;
  transcript: string;
  entities: string[];
  thumbnailUrl: string;
  hasFace: boolean;
}

export interface SearchResponse {
  queryId: string;
  results: SearchResult[];
  expandedCluster?: SearchResult[];
  timing: {
    stage1Visual: number;
    stage2Face: number;
    stage3Text: number;
    total: number;
  };
}

export interface Job {
  id: string;
  videoId: string;
  type: JobType;
  status: JobStatus;
  progress: number;
  error?: string;
  createdAt: string;
  updatedAt: string;
}

export type JobType =
  | 'index-video'
  | 'detect-scenes'
  | 'transcribe'
  | 'embed-visual'
  | 'embed-text'
  | 'detect-faces';

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface ApiKey {
  id: string;
  teamId: string;
  name: string;
  prefix: string;
  createdAt: string;
  lastUsedAt?: string;
}
