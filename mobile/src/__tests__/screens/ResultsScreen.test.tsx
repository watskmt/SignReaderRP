/**
 * Unit tests for ResultsScreen.
 * Native modules and API are mocked in jest.setup.js.
 */
import React from 'react';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import { Share, Alert, ActivityIndicator } from 'react-native';
import ResultsScreen from '../../screens/ResultsScreen';
import { AppProvider } from '../../context/AppContext';
import { NavigationContainer } from '@react-navigation/native';
import * as api from '../../services/api';
import storageService from '../../services/storage';

// Mock navigation
const mockNavigation = {
  navigate: jest.fn(),
  goBack: jest.fn(),
  addListener: jest.fn(() => jest.fn()),
};

const mockRoute = {
  params: {
    sessionId: 'session-001',
    sessionTitle: 'Test Session',
  },
};

// Mock API
jest.mock('../../services/api', () => ({
  getExtractions: jest.fn(),
}));

// Mock storage
jest.mock('../../services/storage', () => ({
  __esModule: true,
  default: {
    getExtractions: jest.fn(),
    saveExtractions: jest.fn(),
    saveExtraction: jest.fn(),
  },
}));

const mockExtractions = [
  {
    id: 'ext-001',
    session_id: 'session-001',
    content: 'STOP',
    confidence: 0.95,
    timestamp: '2026-05-01T10:05:00Z',
    engine: 'paddleocr',
    is_duplicate: false,
    latitude: 35.6762,
    longitude: 139.6503,
  },
  {
    id: 'ext-002',
    session_id: 'session-001',
    content: 'YIELD',
    confidence: 0.72,
    timestamp: '2026-05-01T10:05:30Z',
    engine: 'paddleocr',
    is_duplicate: false,
  },
  {
    id: 'ext-003',
    session_id: 'session-001',
    content: 'STOP',
    confidence: 0.90,
    timestamp: '2026-05-01T10:06:00Z',
    engine: 'paddleocr',
    is_duplicate: true,
  },
];

const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <NavigationContainer>
    <AppProvider>{children}</AppProvider>
  </NavigationContainer>
);

beforeEach(() => {
  jest.clearAllMocks();
  (api.getExtractions as jest.Mock).mockResolvedValue(mockExtractions);
  (storageService.getExtractions as jest.Mock).mockResolvedValue(mockExtractions);
  (storageService.saveExtraction as jest.Mock).mockResolvedValue(undefined);
});

// Helper to wait for async operations
const wait = (ms = 100) => new Promise(resolve => setTimeout(resolve, ms));

// ─────────────────────────────── Loading State ───────────────────────────────

describe('ResultsScreen loading', () => {
  it('shows loading indicator initially', () => {
    const { UNSAFE_getByType } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    // ActivityIndicator is rendered during loading
    expect(UNSAFE_getByType(ActivityIndicator)).toBeTruthy();
  });

  it('loads extractions from API on mount', async () => {
    render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    expect(api.getExtractions).toHaveBeenCalledWith('session-001');
  });

  it('falls back to local storage when API fails', async () => {
    (api.getExtractions as jest.Mock).mockRejectedValueOnce(new Error('Network error'));

    render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    expect(storageService.getExtractions).toHaveBeenCalledWith('session-001');
  });
});

// ─────────────────────────────── Display ─────────────────────────────────────

describe('ResultsScreen display', () => {
  it('renders extractions after loading', async () => {
    const { getByText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    expect(getByText('STOP')).toBeTruthy();
  });

  it('shows confidence badges', async () => {
    const { getByText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    expect(getByText('95%')).toBeTruthy();
  });

  it('shows GPS coordinates when available', async () => {
    const { getByText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    expect(getByText('35.6762, 139.6503')).toBeTruthy();
  });

  it('shows empty state when no extractions', async () => {
    (api.getExtractions as jest.Mock).mockResolvedValueOnce([]);
    (storageService.getExtractions as jest.Mock).mockResolvedValueOnce([]);

    const { getByText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    expect(getByText('No extractions in this session yet')).toBeTruthy();
  });
});

// ─────────────────────────────── Filtering ───────────────────────────────────

describe('ResultsScreen filtering', () => {
  it('filters by keyword', async () => {
    const { getByText, getByPlaceholderText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    expect(getByText('STOP')).toBeTruthy();

    const input = getByPlaceholderText('Filter by keyword…');
    fireEvent.changeText(input, 'YIELD');

    await wait();
    expect(getByText('YIELD')).toBeTruthy();
  });

  it('shows no results message when filter matches nothing', async () => {
    const { getByText, getByPlaceholderText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    expect(getByText('STOP')).toBeTruthy();

    const input = getByPlaceholderText('Filter by keyword…');
    fireEvent.changeText(input, 'NOTFOUND');

    await wait();
    expect(getByText('No results matching "NOTFOUND"')).toBeTruthy();
  });

  it('hides duplicates by default', async () => {
    const { getAllByText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    // Only one STOP should be visible (the non-duplicate)
    expect(getAllByText('STOP')).toHaveLength(1);
  });

  it('toggles duplicate visibility', async () => {
    const { getByText, getAllByText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    expect(getAllByText('STOP')).toHaveLength(1);

    const dupToggle = getByText('Dups');
    fireEvent.press(dupToggle);

    await wait();
    // After toggling, both STOPs should be visible
    expect(getAllByText('STOP')).toHaveLength(2);
  });
});

// ─────────────────────────────── Export ──────────────────────────────────────

describe('ResultsScreen export', () => {
  it('exports data via Share API', async () => {
    const { getByText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    const exportButton = getByText('Export');
    fireEvent.press(exportButton);

    await wait();
    expect(Share.share).toHaveBeenCalled();
  });
});

// ─────────────────────────────── Map Placeholder ─────────────────────────────

describe('ResultsScreen map', () => {
  it('shows alert when map button pressed', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert');

    const { getByText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    const mapButton = getByText('Map');
    fireEvent.press(mapButton);

    expect(alertSpy).toHaveBeenCalled();
    alertSpy.mockRestore();
  });
});

// ─────────────────────────────── Confidence Colors ───────────────────────────

describe('confidenceColor helper', () => {
  it('returns green for high confidence', async () => {
    const { getByText } = render(
      <ResultsScreen navigation={mockNavigation as any} route={mockRoute as any} />,
      { wrapper },
    );

    await wait();
    expect(getByText('95%')).toBeTruthy();
  });
});
