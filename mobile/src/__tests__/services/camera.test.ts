/**
 * Unit tests for CameraService.
 * Native modules (vision-camera, geolocation, permissions) are mocked in jest.setup.js.
 */
import { Platform } from 'react-native';
import Geolocation from '@react-native-community/geolocation';
import { check, PERMISSIONS, request, RESULTS } from 'react-native-permissions';
import { Camera } from 'react-native-vision-camera';
import { CameraService } from '../../services/camera';

// Mock fetch for reading photo files
global.fetch = jest.fn();

// Mock FileReader for jsdom environment
const MockFileReader = jest.fn().mockImplementation(() => ({
  readAsDataURL: jest.fn(),
  onloadend: null as (() => void) | null,
  onerror: null as (() => void) | null,
  result: 'data:image/jpeg;base64,YWJjZGVmZw==',
}));

(global as any).FileReader = MockFileReader;

// Mock Camera.requestCameraPermission as a static method
const mockRequestCameraPermission = jest.fn();
(Camera as any).requestCameraPermission = mockRequestCameraPermission;

let cameraService: CameraService;

beforeEach(() => {
  cameraService = new CameraService();
  jest.clearAllMocks();
  mockRequestCameraPermission.mockReset();
});

// ─────────────────────────────── requestCameraPermission ─────────────────────

describe('requestCameraPermission', () => {
  it('returns true when permission is granted', async () => {
    mockRequestCameraPermission.mockResolvedValueOnce('granted');

    const result = await cameraService.requestCameraPermission();

    expect(result).toBe(true);
    expect(mockRequestCameraPermission).toHaveBeenCalledTimes(1);
  });

  it('returns false when permission is denied', async () => {
    mockRequestCameraPermission.mockResolvedValueOnce('denied');

    const result = await cameraService.requestCameraPermission();

    expect(result).toBe(false);
  });

  it('returns false when permission is blocked', async () => {
    mockRequestCameraPermission.mockResolvedValueOnce('blocked');

    const result = await cameraService.requestCameraPermission();

    expect(result).toBe(false);
  });
});

// ─────────────────────────────── requestLocationPermission ───────────────────

describe('requestLocationPermission', () => {
  it('returns true when already granted on iOS', async () => {
    const originalOS = Platform.OS;
    Object.defineProperty(Platform, 'OS', { value: 'ios' });

    (check as jest.Mock).mockResolvedValueOnce(RESULTS.GRANTED);

    const result = await cameraService.requestLocationPermission();

    expect(result).toBe(true);
    expect(check).toHaveBeenCalled();
    expect(request).not.toHaveBeenCalled();

    Object.defineProperty(Platform, 'OS', { value: originalOS });
  });

  it('requests permission when not granted on iOS', async () => {
    const originalOS = Platform.OS;
    Object.defineProperty(Platform, 'OS', { value: 'ios' });

    (check as jest.Mock).mockResolvedValueOnce(RESULTS.DENIED);
    (request as jest.Mock).mockResolvedValueOnce(RESULTS.GRANTED);

    const result = await cameraService.requestLocationPermission();

    expect(result).toBe(true);
    expect(check).toHaveBeenCalledWith(PERMISSIONS.IOS.LOCATION_WHEN_IN_USE);
    expect(request).toHaveBeenCalledWith(PERMISSIONS.IOS.LOCATION_WHEN_IN_USE);

    Object.defineProperty(Platform, 'OS', { value: originalOS });
  });

  it('requests permission when not granted on Android', async () => {
    const originalOS = Platform.OS;
    Object.defineProperty(Platform, 'OS', { value: 'android' });

    (check as jest.Mock).mockResolvedValueOnce(RESULTS.DENIED);
    (request as jest.Mock).mockResolvedValueOnce(RESULTS.GRANTED);

    const result = await cameraService.requestLocationPermission();

    expect(result).toBe(true);
    expect(check).toHaveBeenCalledWith(PERMISSIONS.ANDROID.ACCESS_FINE_LOCATION);
    expect(request).toHaveBeenCalledWith(PERMISSIONS.ANDROID.ACCESS_FINE_LOCATION);

    Object.defineProperty(Platform, 'OS', { value: originalOS });
  });

  it('returns false when location permission is denied', async () => {
    const originalOS = Platform.OS;
    Object.defineProperty(Platform, 'OS', { value: 'ios' });

    (check as jest.Mock).mockResolvedValueOnce(RESULTS.DENIED);
    (request as jest.Mock).mockResolvedValueOnce(RESULTS.DENIED);

    const result = await cameraService.requestLocationPermission();

    expect(result).toBe(false);

    Object.defineProperty(Platform, 'OS', { value: originalOS });
  });
});

// ─────────────────────────────── getCurrentLocation ──────────────────────────

describe('getCurrentLocation', () => {
  it('returns GPS coordinates on success', async () => {
    const mockPosition = {
      coords: {
        latitude: 35.6762,
        longitude: 139.6503,
        altitude: 42.0,
      },
    };

    (Geolocation.getCurrentPosition as jest.Mock).mockImplementation(
      (success) => success(mockPosition),
    );

    const result = await cameraService.getCurrentLocation();

    expect(result.latitude).toBe(35.6762);
    expect(result.longitude).toBe(139.6503);
    expect(result.altitude).toBe(42.0);
  });

  it('returns null altitude when not available', async () => {
    const mockPosition = {
      coords: {
        latitude: 35.0,
        longitude: 139.0,
        altitude: null,
      },
    };

    (Geolocation.getCurrentPosition as jest.Mock).mockImplementation(
      (success) => success(mockPosition),
    );

    const result = await cameraService.getCurrentLocation();

    expect(result.latitude).toBe(35.0);
    expect(result.longitude).toBe(139.0);
    expect(result.altitude).toBeNull();
  });

  it('rejects with error message on failure', async () => {
    const mockError = {
      code: 2,
      message: 'Position unavailable',
    };

    (Geolocation.getCurrentPosition as jest.Mock).mockImplementation(
      (_success, error) => error(mockError),
    );

    await expect(cameraService.getCurrentLocation()).rejects.toThrow(
      'Location error (2): Position unavailable',
    );
  });
});

// ─────────────────────────────── captureFrame ────────────────────────────────

describe('captureFrame', () => {
  it('captures frame and returns base64 string', async () => {
    const mockCameraRef = {
      current: {
        takePhoto: jest.fn().mockResolvedValue({ path: '/test/photo.jpg' }),
      },
    };

    const mockBlob = new Blob(['fake-image-data'], { type: 'image/jpeg' });
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      blob: () => Promise.resolve(mockBlob),
    });

    // Setup FileReader mock to resolve with base64
    const mockReader = {
      readAsDataURL: jest.fn(),
      onloadend: null as (() => void) | null,
      onerror: null as (() => void) | null,
      result: 'data:image/jpeg;base64,YWJjZGVmZw==',
    };

    MockFileReader.mockImplementation(() => mockReader);

    const resultPromise = cameraService.captureFrame(mockCameraRef as any);

    // Simulate FileReader onload
    setTimeout(() => {
      if (mockReader.onloadend) {
        mockReader.onloadend();
      }
    }, 0);

    const result = await resultPromise;

    expect(mockCameraRef.current.takePhoto).toHaveBeenCalledWith({
      flash: 'off',
      enableShutterSound: false,
    });
    expect(result).toBe('YWJjZGVmZw==');
  });

  it('throws error when camera ref is null', async () => {
    const mockCameraRef = { current: null };

    await expect(
      cameraService.captureFrame(mockCameraRef as any),
    ).rejects.toThrow('Camera reference is not available');
  });

  it('throws error when fetch fails', async () => {
    const mockCameraRef = {
      current: {
        takePhoto: jest.fn().mockResolvedValue({ path: '/test/photo.jpg' }),
      },
    };

    (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('File not found'));

    await expect(cameraService.captureFrame(mockCameraRef as any)).rejects.toThrow(
      'File not found',
    );
  });
});

// ─────────────────────────────── startFrameCapture ───────────────────────────

describe('startFrameCapture', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('returns an interval ID', () => {
    const mockCameraRef = {
      current: {
        takePhoto: jest.fn().mockResolvedValue({ path: '/test/photo.jpg' }),
      },
    };

    const callback = jest.fn();

    const intervalId = cameraService.startFrameCapture(mockCameraRef as any, 1000, callback);

    expect(intervalId).toBeDefined();
    expect(typeof intervalId).toBe('object'); // Node.js returns a Timeout object
  });

  it('silently skips failed frames', async () => {
    const mockCameraRef = {
      current: {
        takePhoto: jest.fn().mockRejectedValue(new Error('Camera busy')),
      },
    };

    const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation();
    const callback = jest.fn();

    cameraService.startFrameCapture(mockCameraRef as any, 1000, callback);

    await jest.advanceTimersByTimeAsync(1000);

    expect(callback).not.toHaveBeenCalled();
    expect(consoleWarnSpy).toHaveBeenCalled();

    consoleWarnSpy.mockRestore();
  });
});

// ─────────────────────────────── stopFrameCapture ────────────────────────────

describe('stopFrameCapture', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('clears the interval', () => {
    const mockCameraRef = {
      current: {
        takePhoto: jest.fn().mockResolvedValue({ path: '/test/photo.jpg' }),
      },
    };

    const callback = jest.fn();
    const intervalId = cameraService.startFrameCapture(
      mockCameraRef as any,
      1000,
      callback,
    );

    cameraService.stopFrameCapture(intervalId);

    jest.advanceTimersByTime(2000);

    expect(callback).not.toHaveBeenCalled();
  });
});
