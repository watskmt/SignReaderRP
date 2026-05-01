/**
 * AppContext — global application state for the active session, extracted
 * texts, recording status, and GPS toggle.
 */
import React, {
  createContext,
  ReactNode,
  useContext,
  useReducer,
} from 'react';

// ─────────────────────────────── Types ───────────────────────────────────────

export interface SessionData {
  id: string;
  title: string;
  description?: string;
  status: string;
  started_at: string;
  ended_at?: string | null;
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
}

interface AppState {
  currentSession: SessionData | null;
  extractions: ExtractionData[];
  isRecording: boolean;
  gpsEnabled: boolean;
}

type AppAction =
  | { type: 'SET_SESSION'; payload: SessionData | null }
  | { type: 'ADD_EXTRACTION'; payload: ExtractionData }
  | { type: 'CLEAR_EXTRACTIONS' }
  | { type: 'SET_RECORDING'; payload: boolean }
  | { type: 'SET_GPS_ENABLED'; payload: boolean };

interface AppContextValue extends AppState {
  setCurrentSession: (session: SessionData | null) => void;
  addExtraction: (extraction: ExtractionData) => void;
  clearExtractions: () => void;
  setRecording: (value: boolean) => void;
  setGpsEnabled: (value: boolean) => void;
}

// ─────────────────────────────── Reducer ─────────────────────────────────────

const initialState: AppState = {
  currentSession: null,
  extractions: [],
  isRecording: false,
  gpsEnabled: false,
};

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_SESSION':
      return { ...state, currentSession: action.payload };

    case 'ADD_EXTRACTION':
      // Avoid adding duplicates to local state
      if (state.extractions.some((e) => e.id === action.payload.id)) {
        return state;
      }
      return { ...state, extractions: [...state.extractions, action.payload] };

    case 'CLEAR_EXTRACTIONS':
      return { ...state, extractions: [] };

    case 'SET_RECORDING':
      return { ...state, isRecording: action.payload };

    case 'SET_GPS_ENABLED':
      return { ...state, gpsEnabled: action.payload };

    default:
      return state;
  }
}

// ─────────────────────────────── Context ─────────────────────────────────────

const AppContext = createContext<AppContextValue | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  const value: AppContextValue = {
    ...state,
    setCurrentSession: (session) =>
      dispatch({ type: 'SET_SESSION', payload: session }),
    addExtraction: (extraction) =>
      dispatch({ type: 'ADD_EXTRACTION', payload: extraction }),
    clearExtractions: () => dispatch({ type: 'CLEAR_EXTRACTIONS' }),
    setRecording: (value) => dispatch({ type: 'SET_RECORDING', payload: value }),
    setGpsEnabled: (value) =>
      dispatch({ type: 'SET_GPS_ENABLED', payload: value }),
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext(): AppContextValue {
  const ctx = useContext(AppContext);
  if (ctx === undefined) {
    throw new Error('useAppContext must be used within an AppProvider');
  }
  return ctx;
}

export default AppContext;
