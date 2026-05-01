/**
 * API service — typed wrappers around the SignReader backend REST API.
 */
import apiClient from '../config/api';

// ─────────────────────────────── Response types ───────────────────────────────

export interface HealthResponse {
  status: string;
  version: string;
  ocr_engine: string;
}

export interface SessionResponse {
  id: string;
  user_id?: string | null;
  title: string;
  description?: string | null;
  status: string;
  started_at: string;
  ended_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TextResult {
  content: string;
  confidence: number;
  bounding_box?: unknown;
}

export interface OCRResponse {
  status: string;
  texts: TextResult[];
  processing_time_ms: number;
  engine: string;
}

export interface TaskResponse {
  task_id: string;
  status: string;
  message: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: string;
  result?: unknown;
  error?: string | null;
}

export interface ExtractionResponse {
  id: string;
  session_id: string;
  content: string;
  confidence: number;
  bounding_box?: unknown;
  latitude?: number | null;
  longitude?: number | null;
  altitude?: number | null;
  timestamp: string;
  engine: string;
  is_duplicate: boolean;
  created_at: string;
}

// ─────────────────────────────── Request types ────────────────────────────────

export interface CreateSessionRequest {
  title: string;
  description?: string;
  user_id?: string;
}

export interface SaveExtractionRequest {
  session_id: string;
  content: string;
  confidence: number;
  bounding_box?: unknown;
  latitude?: number | null;
  longitude?: number | null;
  altitude?: number | null;
  engine?: string;
}

// ─────────────────────────────── API functions ────────────────────────────────

export async function healthCheck(): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>('/health');
  return response.data;
}

export async function createSession(
  data: CreateSessionRequest,
): Promise<SessionResponse> {
  const response = await apiClient.post<SessionResponse>('/sessions', data);
  return response.data;
}

export async function getSession(id: string): Promise<SessionResponse> {
  const response = await apiClient.get<SessionResponse>(`/sessions/${id}`);
  return response.data;
}

export async function processOCRAsync(
  frame_b64: string,
  session_id: string,
  latitude?: number | null,
  longitude?: number | null,
): Promise<TaskResponse> {
  const response = await apiClient.post<TaskResponse>('/ocr/process/async', {
    frame: frame_b64,
    session_id,
    latitude: latitude ?? undefined,
    longitude: longitude ?? undefined,
  });
  return response.data;
}

export async function getTaskStatus(task_id: string): Promise<TaskStatusResponse> {
  const response = await apiClient.get<TaskStatusResponse>(`/tasks/${task_id}`);
  return response.data;
}

export async function saveExtraction(
  data: SaveExtractionRequest,
): Promise<ExtractionResponse> {
  const response = await apiClient.post<ExtractionResponse>('/extract/save', data);
  return response.data;
}

export async function getExtractions(
  session_id: string,
): Promise<ExtractionResponse[]> {
  const response = await apiClient.get<ExtractionResponse[]>(
    `/extract/${session_id}`,
  );
  return response.data;
}

export async function setFilterKeywords(
  session_id: string,
  keywords: string[],
  mode: 'include' | 'exclude' = 'include',
): Promise<void> {
  await apiClient.post('/filters/keywords', { session_id, keywords, mode });
}
