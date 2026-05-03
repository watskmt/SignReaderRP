/**
 * Unit tests for AppContext.
 * Tests the reducer logic and context hooks.
 */
import React from 'react';
import { renderHook, act } from '@testing-library/react-native';
import { AppProvider, useAppContext, SessionData, ExtractionData } from '../../context/AppContext';

const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AppProvider>{children}</AppProvider>
);

// ─────────────────────────────── Initial State ───────────────────────────────

describe('AppContext initial state', () => {
  it('starts with null session', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    expect(result.current.currentSession).toBeNull();
  });

  it('starts with empty extractions array', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    expect(result.current.extractions).toEqual([]);
  });

  it('starts with isRecording false', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    expect(result.current.isRecording).toBe(false);
  });

  it('starts with gpsEnabled false', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    expect(result.current.gpsEnabled).toBe(false);
  });
});

// ─────────────────────────────── setCurrentSession ───────────────────────────

describe('setCurrentSession', () => {
  it('sets the current session', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const session: SessionData = {
      id: 'session-001',
      title: 'Test Walk',
      status: 'active',
      started_at: '2026-05-01T10:00:00Z',
    };

    act(() => {
      result.current.setCurrentSession(session);
    });

    expect(result.current.currentSession).toEqual(session);
  });

  it('can set session to null', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const session: SessionData = {
      id: 'session-001',
      title: 'Test Walk',
      status: 'active',
      started_at: '2026-05-01T10:00:00Z',
    };

    act(() => {
      result.current.setCurrentSession(session);
    });

    act(() => {
      result.current.setCurrentSession(null);
    });

    expect(result.current.currentSession).toBeNull();
  });

  it('replaces previous session', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const session1: SessionData = {
      id: 'session-001',
      title: 'First Walk',
      status: 'active',
      started_at: '2026-05-01T10:00:00Z',
    };

    const session2: SessionData = {
      id: 'session-002',
      title: 'Second Walk',
      status: 'active',
      started_at: '2026-05-01T11:00:00Z',
    };

    act(() => {
      result.current.setCurrentSession(session1);
    });

    act(() => {
      result.current.setCurrentSession(session2);
    });

    expect(result.current.currentSession?.id).toBe('session-002');
    expect(result.current.currentSession?.title).toBe('Second Walk');
  });
});

// ─────────────────────────────── addExtraction ───────────────────────────────

describe('addExtraction', () => {
  it('adds an extraction to the list', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const extraction: ExtractionData = {
      id: 'ext-001',
      session_id: 'session-001',
      content: 'STOP',
      confidence: 0.95,
      timestamp: '2026-05-01T10:05:00Z',
      engine: 'paddleocr',
      is_duplicate: false,
    };

    act(() => {
      result.current.addExtraction(extraction);
    });

    expect(result.current.extractions).toHaveLength(1);
    expect(result.current.extractions[0].content).toBe('STOP');
  });

  it('adds multiple extractions', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const extraction1: ExtractionData = {
      id: 'ext-001',
      session_id: 'session-001',
      content: 'STOP',
      confidence: 0.95,
      timestamp: '2026-05-01T10:05:00Z',
      engine: 'paddleocr',
      is_duplicate: false,
    };

    const extraction2: ExtractionData = {
      id: 'ext-002',
      session_id: 'session-001',
      content: 'YIELD',
      confidence: 0.88,
      timestamp: '2026-05-01T10:05:01Z',
      engine: 'paddleocr',
      is_duplicate: false,
    };

    act(() => {
      result.current.addExtraction(extraction1);
    });

    act(() => {
      result.current.addExtraction(extraction2);
    });

    expect(result.current.extractions).toHaveLength(2);
    expect(result.current.extractions[1].content).toBe('YIELD');
  });

  it('prevents duplicate extractions by id', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const extraction: ExtractionData = {
      id: 'ext-001',
      session_id: 'session-001',
      content: 'STOP',
      confidence: 0.95,
      timestamp: '2026-05-01T10:05:00Z',
      engine: 'paddleocr',
      is_duplicate: false,
    };

    act(() => {
      result.current.addExtraction(extraction);
    });

    // Try to add the same extraction again
    act(() => {
      result.current.addExtraction(extraction);
    });

    expect(result.current.extractions).toHaveLength(1);
  });

  it('allows different extractions with same content', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const extraction1: ExtractionData = {
      id: 'ext-001',
      session_id: 'session-001',
      content: 'STOP',
      confidence: 0.95,
      timestamp: '2026-05-01T10:05:00Z',
      engine: 'paddleocr',
      is_duplicate: false,
    };

    const extraction2: ExtractionData = {
      id: 'ext-002',
      session_id: 'session-001',
      content: 'STOP',
      confidence: 0.90,
      timestamp: '2026-05-01T10:05:01Z',
      engine: 'paddleocr',
      is_duplicate: false,
    };

    act(() => {
      result.current.addExtraction(extraction1);
    });

    act(() => {
      result.current.addExtraction(extraction2);
    });

    expect(result.current.extractions).toHaveLength(2);
  });
});

// ─────────────────────────────── clearExtractions ────────────────────────────

describe('clearExtractions', () => {
  it('removes all extractions', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const extraction: ExtractionData = {
      id: 'ext-001',
      session_id: 'session-001',
      content: 'STOP',
      confidence: 0.95,
      timestamp: '2026-05-01T10:05:00Z',
      engine: 'paddleocr',
      is_duplicate: false,
    };

    act(() => {
      result.current.addExtraction(extraction);
    });

    expect(result.current.extractions).toHaveLength(1);

    act(() => {
      result.current.clearExtractions();
    });

    expect(result.current.extractions).toEqual([]);
  });

  it('does not affect current session', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const session: SessionData = {
      id: 'session-001',
      title: 'Test Walk',
      status: 'active',
      started_at: '2026-05-01T10:00:00Z',
    };

    act(() => {
      result.current.setCurrentSession(session);
    });

    act(() => {
      result.current.clearExtractions();
    });

    expect(result.current.currentSession).not.toBeNull();
    expect(result.current.currentSession?.id).toBe('session-001');
  });
});

// ─────────────────────────────── setRecording ────────────────────────────────

describe('setRecording', () => {
  it('sets recording to true', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    act(() => {
      result.current.setRecording(true);
    });

    expect(result.current.isRecording).toBe(true);
  });

  it('sets recording to false', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    act(() => {
      result.current.setRecording(true);
    });

    act(() => {
      result.current.setRecording(false);
    });

    expect(result.current.isRecording).toBe(false);
  });

  it('does not affect other state', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const extraction: ExtractionData = {
      id: 'ext-001',
      session_id: 'session-001',
      content: 'STOP',
      confidence: 0.95,
      timestamp: '2026-05-01T10:05:00Z',
      engine: 'paddleocr',
      is_duplicate: false,
    };

    act(() => {
      result.current.addExtraction(extraction);
    });

    act(() => {
      result.current.setRecording(true);
    });

    expect(result.current.extractions).toHaveLength(1);
    expect(result.current.isRecording).toBe(true);
  });
});

// ─────────────────────────────── setGpsEnabled ───────────────────────────────

describe('setGpsEnabled', () => {
  it('enables GPS', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    act(() => {
      result.current.setGpsEnabled(true);
    });

    expect(result.current.gpsEnabled).toBe(true);
  });

  it('disables GPS', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    act(() => {
      result.current.setGpsEnabled(true);
    });

    act(() => {
      result.current.setGpsEnabled(false);
    });

    expect(result.current.gpsEnabled).toBe(false);
  });

  it('does not affect other state', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    const session: SessionData = {
      id: 'session-001',
      title: 'Test Walk',
      status: 'active',
      started_at: '2026-05-01T10:00:00Z',
    };

    act(() => {
      result.current.setCurrentSession(session);
    });

    act(() => {
      result.current.setGpsEnabled(true);
    });

    expect(result.current.currentSession?.id).toBe('session-001');
    expect(result.current.gpsEnabled).toBe(true);
  });
});

// ─────────────────────────────── useAppContext Error ─────────────────────────

describe('useAppContext error handling', () => {
  it('throws when used outside AppProvider', () => {
    // Suppress console.error for this test
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();

    expect(() => {
      renderHook(() => useAppContext());
    }).toThrow('useAppContext must be used within an AppProvider');

    consoleErrorSpy.mockRestore();
  });
});

// ─────────────────────────────── Integration ─────────────────────────────────

describe('AppContext integration', () => {
  it('full workflow: session -> recording -> extractions -> cleanup', () => {
    const { result } = renderHook(() => useAppContext(), { wrapper });

    // Start a session
    const session: SessionData = {
      id: 'session-001',
      title: 'Downtown Walk',
      status: 'active',
      started_at: '2026-05-01T10:00:00Z',
    };

    act(() => {
      result.current.setCurrentSession(session);
    });

    expect(result.current.currentSession?.id).toBe('session-001');

    // Enable GPS and start recording
    act(() => {
      result.current.setGpsEnabled(true);
    });

    act(() => {
      result.current.setRecording(true);
    });

    expect(result.current.gpsEnabled).toBe(true);
    expect(result.current.isRecording).toBe(true);

    // Add extractions
    const extraction1: ExtractionData = {
      id: 'ext-001',
      session_id: 'session-001',
      content: 'STOP',
      confidence: 0.95,
      timestamp: '2026-05-01T10:05:00Z',
      engine: 'paddleocr',
      is_duplicate: false,
    };

    const extraction2: ExtractionData = {
      id: 'ext-002',
      session_id: 'session-001',
      content: 'SPEED LIMIT 50',
      confidence: 0.88,
      timestamp: '2026-05-01T10:05:01Z',
      engine: 'paddleocr',
      is_duplicate: false,
    };

    act(() => {
      result.current.addExtraction(extraction1);
    });

    act(() => {
      result.current.addExtraction(extraction2);
    });

    expect(result.current.extractions).toHaveLength(2);

    // Stop recording and clear extractions
    act(() => {
      result.current.setRecording(false);
    });

    act(() => {
      result.current.clearExtractions();
    });

    expect(result.current.isRecording).toBe(false);
    expect(result.current.extractions).toEqual([]);
    expect(result.current.currentSession?.id).toBe('session-001');
  });
});
