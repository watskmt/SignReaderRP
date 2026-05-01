/**
 * Unit tests for LocalStorageService.
 * AsyncStorage is mocked in jest.setup.js.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { LocalStorageService, SessionData, ExtractionData } from '../../services/storage';

// Use a fresh service instance per test (not the singleton default export)
let storage: LocalStorageService;

const SESSIONS_KEY = '@signreader:sessions';
const CURRENT_SESSION_KEY = '@signreader:currentSessionId';

function extractionKey(id: string) {
  return `@signreader:extractions:${id}`;
}

const mockSession: SessionData = {
  id: 'session-001',
  title: 'Test Walk',
  status: 'active',
  started_at: '2026-05-01T10:00:00Z',
};

const mockExtraction: ExtractionData = {
  id: 'ext-001',
  session_id: 'session-001',
  content: 'STOP',
  confidence: 0.98,
  timestamp: '2026-05-01T10:05:00Z',
  engine: 'paddleocr',
  is_duplicate: false,
};

beforeEach(() => {
  storage = new LocalStorageService();
  jest.resetAllMocks();
  // Restore default return values after reset
  (AsyncStorage.setItem as jest.Mock).mockResolvedValue(undefined);
  (AsyncStorage.getItem as jest.Mock).mockResolvedValue(null);
  (AsyncStorage.removeItem as jest.Mock).mockResolvedValue(undefined);
});

// ─────────────────────────────── saveSession ─────────────────────────────────

test('saveSession stores correctly', async () => {
  (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(null);

  await storage.saveSession(mockSession);

  expect(AsyncStorage.setItem).toHaveBeenCalledWith(
    SESSIONS_KEY,
    JSON.stringify([mockSession]),
  );
});

// ─────────────────────────────── getSession ──────────────────────────────────

test('getSession retrieves correctly', async () => {
  (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(
    JSON.stringify([mockSession]),
  );

  const result = await storage.getSession('session-001');
  expect(result).not.toBeNull();
  expect(result?.id).toBe('session-001');
  expect(result?.title).toBe('Test Walk');
});

test('getSession returns null when not found', async () => {
  (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(
    JSON.stringify([mockSession]),
  );

  const result = await storage.getSession('nonexistent-id');
  expect(result).toBeNull();
});

// ─────────────────────────────── getAllSessions ───────────────────────────────

test('getAllSessions returns all', async () => {
  const sessions: SessionData[] = [
    mockSession,
    { ...mockSession, id: 'session-002', title: 'Session 2' },
  ];
  (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(
    JSON.stringify(sessions),
  );

  const result = await storage.getAllSessions();
  expect(result).toHaveLength(2);
});

test('getAllSessions returns empty array when storage empty', async () => {
  (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(null);

  const result = await storage.getAllSessions();
  expect(result).toEqual([]);
});

// ─────────────────────────────── deleteSession ───────────────────────────────

test('deleteSession removes session and its extractions', async () => {
  const sessions = [mockSession];
  (AsyncStorage.getItem as jest.Mock)
    .mockResolvedValueOnce(JSON.stringify(sessions)) // getAllSessions call
    .mockResolvedValueOnce(null);                    // getExtractions call

  await storage.deleteSession('session-001');

  // Should call setItem with empty array (session removed)
  expect(AsyncStorage.setItem).toHaveBeenCalledWith(
    SESSIONS_KEY,
    JSON.stringify([]),
  );
  // Should call removeItem for extraction key
  expect(AsyncStorage.removeItem).toHaveBeenCalledWith(
    extractionKey('session-001'),
  );
});

test('deleteSession with no extractions completes without error', async () => {
  const sessions = [mockSession];
  (AsyncStorage.getItem as jest.Mock)
    .mockResolvedValueOnce(JSON.stringify(sessions))
    .mockResolvedValueOnce(null); // No extractions

  await expect(storage.deleteSession('session-001')).resolves.toBeUndefined();
});

// ─────────────────────────────── saveExtraction ──────────────────────────────

test('saveExtraction stores correctly', async () => {
  (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(null);

  await storage.saveExtraction(mockExtraction);

  expect(AsyncStorage.setItem).toHaveBeenCalledWith(
    extractionKey('session-001'),
    JSON.stringify([mockExtraction]),
  );
});

test('saveExtraction appends to existing', async () => {
  const existing: ExtractionData[] = [mockExtraction];
  (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(
    JSON.stringify(existing),
  );

  const second: ExtractionData = {
    ...mockExtraction,
    id: 'ext-002',
    content: 'YIELD',
  };

  await storage.saveExtraction(second);

  expect(AsyncStorage.setItem).toHaveBeenCalledWith(
    extractionKey('session-001'),
    JSON.stringify([mockExtraction, second]),
  );
});

// ─────────────────────────────── getExtractions ──────────────────────────────

test('getExtractions retrieves by session_id', async () => {
  const extractions = [mockExtraction];
  (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(
    JSON.stringify(extractions),
  );

  const result = await storage.getExtractions('session-001');
  expect(result).toHaveLength(1);
  expect(result[0].content).toBe('STOP');
});

test('getExtractions returns empty array when none', async () => {
  (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(null);

  const result = await storage.getExtractions('session-001');
  expect(result).toEqual([]);
});

// ─────────────────────────────── clearSessionExtractions ─────────────────────

test('clearSessionExtractions clears correctly', async () => {
  await storage.clearSessionExtractions('session-001');

  expect(AsyncStorage.removeItem).toHaveBeenCalledWith(
    extractionKey('session-001'),
  );
});

// ─────────────────────────────── current session id ──────────────────────────

test('setCurrentSessionId and getCurrentSessionId round-trip', async () => {
  (AsyncStorage.setItem as jest.Mock).mockResolvedValueOnce(undefined);
  (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce('session-001');

  await storage.setCurrentSessionId('session-001');
  const result = await storage.getCurrentSessionId();

  expect(AsyncStorage.setItem).toHaveBeenCalledWith(
    CURRENT_SESSION_KEY,
    'session-001',
  );
  expect(result).toBe('session-001');
});
