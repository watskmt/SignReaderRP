/**
 * LocalStorageService — AsyncStorage-backed persistence for sessions
 * and extractions, providing an offline-first data layer.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

export interface SessionData {
  id: string;
  title: string;
  description?: string | null;
  status: string;
  started_at: string;
  ended_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ExtractionData {
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
  created_at?: string;
}

const SESSIONS_KEY = '@signreader:sessions';
const EXTRACTIONS_PREFIX = '@signreader:extractions:';
const CURRENT_SESSION_KEY = '@signreader:currentSessionId';

export class LocalStorageService {
  // ──────────────────────────────── Sessions ───────────────────────────────

  async saveSession(session: SessionData): Promise<void> {
    const existing = await this.getAllSessions();
    const updated = existing.filter((s) => s.id !== session.id);
    updated.push(session);
    await AsyncStorage.setItem(SESSIONS_KEY, JSON.stringify(updated));
  }

  async getSession(id: string): Promise<SessionData | null> {
    const sessions = await this.getAllSessions();
    return sessions.find((s) => s.id === id) ?? null;
  }

  async getAllSessions(): Promise<SessionData[]> {
    const raw = await AsyncStorage.getItem(SESSIONS_KEY);
    if (!raw) {
      return [];
    }
    try {
      return JSON.parse(raw) as SessionData[];
    } catch {
      return [];
    }
  }

  async deleteSession(id: string): Promise<void> {
    const sessions = await this.getAllSessions();
    const updated = sessions.filter((s) => s.id !== id);
    await AsyncStorage.setItem(SESSIONS_KEY, JSON.stringify(updated));

    // Also delete associated extractions
    await this.clearSessionExtractions(id);
  }

  // ──────────────────────────────── Extractions ────────────────────────────

  private _extractionKey(session_id: string): string {
    return `${EXTRACTIONS_PREFIX}${session_id}`;
  }

  async saveExtraction(extraction: ExtractionData): Promise<void> {
    const existing = await this.getExtractions(extraction.session_id);
    const updated = existing.filter((e) => e.id !== extraction.id);
    updated.push(extraction);
    await AsyncStorage.setItem(
      this._extractionKey(extraction.session_id),
      JSON.stringify(updated),
    );
  }

  async getExtractions(session_id: string): Promise<ExtractionData[]> {
    const raw = await AsyncStorage.getItem(this._extractionKey(session_id));
    if (!raw) {
      return [];
    }
    try {
      return JSON.parse(raw) as ExtractionData[];
    } catch {
      return [];
    }
  }

  async clearSessionExtractions(session_id: string): Promise<void> {
    await AsyncStorage.removeItem(this._extractionKey(session_id));
  }

  // ──────────────────────────────── Current session ────────────────────────

  async setCurrentSessionId(id: string): Promise<void> {
    await AsyncStorage.setItem(CURRENT_SESSION_KEY, id);
  }

  async getCurrentSessionId(): Promise<string | null> {
    return AsyncStorage.getItem(CURRENT_SESSION_KEY);
  }
}

export default new LocalStorageService();
