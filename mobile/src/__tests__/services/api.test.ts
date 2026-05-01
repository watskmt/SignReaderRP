/**
 * Unit tests for the API service layer.
 * Axios is mocked globally in jest.setup.js.
 */
import axios from 'axios';
import {
  healthCheck,
  createSession,
  processOCRAsync,
  getTaskStatus,
  saveExtraction,
  getExtractions,
  setFilterKeywords,
} from '../../services/api';

// Cast the mocked axios so TypeScript knows about jest mock methods
const mockedAxios = axios as jest.Mocked<typeof axios>;

// The axios instance returned by axios.create() is the same object as the mock
// (see jest.setup.js where create() returns `mockAxios`)
const mockApiClient = axios as any;

beforeEach(() => {
  jest.clearAllMocks();
});

// ─────────────────────────────── healthCheck ─────────────────────────────────

test('healthCheck returns ok status', async () => {
  mockApiClient.get.mockResolvedValueOnce({
    data: { status: 'ok', version: '0.1.0', ocr_engine: 'paddleocr' },
  });

  const result = await healthCheck();
  expect(result.status).toBe('ok');
  expect(result.version).toBe('0.1.0');
  expect(result.ocr_engine).toBe('paddleocr');
});

// ─────────────────────────────── createSession ───────────────────────────────

test('createSession success', async () => {
  const mockSession = {
    id: 'session-abc',
    title: 'Test Session',
    status: 'active',
    started_at: '2026-05-01T10:00:00Z',
    ended_at: null,
    created_at: '2026-05-01T10:00:00Z',
    updated_at: '2026-05-01T10:00:00Z',
  };

  mockApiClient.post.mockResolvedValueOnce({ data: mockSession });

  const result = await createSession({ title: 'Test Session' });
  expect(result.id).toBe('session-abc');
  expect(result.title).toBe('Test Session');
  expect(result.status).toBe('active');
});

test('createSession network error throws', async () => {
  mockApiClient.post.mockRejectedValueOnce(new Error('Network error'));

  await expect(createSession({ title: 'Fail Session' })).rejects.toThrow(
    'Network error',
  );
});

// ─────────────────────────────── processOCRAsync ─────────────────────────────

test('processOCRAsync returns task_id', async () => {
  const mockTask = {
    task_id: 'task-xyz-123',
    status: 'queued',
    message: 'OCR task queued',
  };

  mockApiClient.post.mockResolvedValueOnce({ data: mockTask });

  const result = await processOCRAsync(
    'base64string',
    'session-abc',
    35.6762,
    139.6503,
  );
  expect(result.task_id).toBe('task-xyz-123');
  expect(result.status).toBe('queued');
});

// ─────────────────────────────── getTaskStatus ───────────────────────────────

test('getTaskStatus returns status', async () => {
  const mockStatus = {
    task_id: 'task-xyz-123',
    status: 'success',
    result: { texts_found: 2 },
    error: null,
  };

  mockApiClient.get.mockResolvedValueOnce({ data: mockStatus });

  const result = await getTaskStatus('task-xyz-123');
  expect(result.task_id).toBe('task-xyz-123');
  expect(result.status).toBe('success');
  expect(result.result).toEqual({ texts_found: 2 });
});

// ─────────────────────────────── saveExtraction ──────────────────────────────

test('saveExtraction success', async () => {
  const mockExtraction = {
    id: 'ext-001',
    session_id: 'session-abc',
    content: 'STOP',
    confidence: 0.98,
    bounding_box: null,
    latitude: null,
    longitude: null,
    altitude: null,
    timestamp: '2026-05-01T10:05:00Z',
    engine: 'paddleocr',
    is_duplicate: false,
    created_at: '2026-05-01T10:05:00Z',
  };

  mockApiClient.post.mockResolvedValueOnce({ data: mockExtraction });

  const result = await saveExtraction({
    session_id: 'session-abc',
    content: 'STOP',
    confidence: 0.98,
  });

  expect(result.id).toBe('ext-001');
  expect(result.content).toBe('STOP');
  expect(result.is_duplicate).toBe(false);
});

// ─────────────────────────────── getExtractions ──────────────────────────────

test('getExtractions returns array', async () => {
  const mockExtractions = [
    {
      id: 'ext-001',
      session_id: 'session-abc',
      content: 'STOP',
      confidence: 0.98,
      bounding_box: null,
      latitude: null,
      longitude: null,
      altitude: null,
      timestamp: '2026-05-01T10:05:00Z',
      engine: 'paddleocr',
      is_duplicate: false,
      created_at: '2026-05-01T10:05:00Z',
    },
    {
      id: 'ext-002',
      session_id: 'session-abc',
      content: 'YIELD',
      confidence: 0.91,
      bounding_box: null,
      latitude: null,
      longitude: null,
      altitude: null,
      timestamp: '2026-05-01T10:05:01Z',
      engine: 'paddleocr',
      is_duplicate: false,
      created_at: '2026-05-01T10:05:01Z',
    },
  ];

  mockApiClient.get.mockResolvedValueOnce({ data: mockExtractions });

  const result = await getExtractions('session-abc');
  expect(Array.isArray(result)).toBe(true);
  expect(result).toHaveLength(2);
  expect(result[0].content).toBe('STOP');
});

// ─────────────────────────────── setFilterKeywords ───────────────────────────

test('setFilterKeywords succeeds', async () => {
  mockApiClient.post.mockResolvedValueOnce({ data: { status: 'ok' } });

  await expect(
    setFilterKeywords('session-abc', ['STOP', 'YIELD'], 'include'),
  ).resolves.toBeUndefined();

  expect(mockApiClient.post).toHaveBeenCalledWith('/filters/keywords', {
    session_id: 'session-abc',
    keywords: ['STOP', 'YIELD'],
    mode: 'include',
  });
});
