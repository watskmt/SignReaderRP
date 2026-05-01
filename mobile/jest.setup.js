/**
 * Jest setup file — mock all native modules that are unavailable in jsdom.
 */

// ─────────────────────────────── AsyncStorage ────────────────────────────────
jest.mock('@react-native-async-storage/async-storage', () => ({
  setItem: jest.fn(() => Promise.resolve()),
  getItem: jest.fn(() => Promise.resolve(null)),
  removeItem: jest.fn(() => Promise.resolve()),
  clear: jest.fn(() => Promise.resolve()),
  getAllKeys: jest.fn(() => Promise.resolve([])),
  multiGet: jest.fn(() => Promise.resolve([])),
  multiSet: jest.fn(() => Promise.resolve()),
  multiRemove: jest.fn(() => Promise.resolve()),
}));

// ─────────────────────────────── Axios ───────────────────────────────────────
jest.mock('axios', () => {
  const mockAxios = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
    create: jest.fn(function () {
      return mockAxios;
    }),
    interceptors: {
      request: { use: jest.fn(), eject: jest.fn() },
      response: { use: jest.fn(), eject: jest.fn() },
    },
    defaults: { headers: { common: {} } },
  };
  return mockAxios;
});

// ─────────────────────────────── react-native-vision-camera ─────────────────
jest.mock('react-native-vision-camera', () => {
  const React = require('react');
  const { View } = require('react-native');

  const Camera = React.forwardRef((props, ref) => {
    React.useImperativeHandle(ref, () => ({
      takePhoto: jest.fn(() =>
        Promise.resolve({ path: '/test/photo.jpg' })
      ),
    }));
    return React.createElement(View, props);
  });

  return {
    Camera,
    useCameraDevice: jest.fn(() => ({})),
    useCameraPermission: jest.fn(() => ({
      hasPermission: true,
      requestPermission: jest.fn(() => Promise.resolve(true)),
    })),
  };
});

// ─────────────────────────────── Geolocation ────────────────────────────────
jest.mock('@react-native-community/geolocation', () => ({
  getCurrentPosition: jest.fn((success) =>
    success({
      coords: {
        latitude: 35.6762,
        longitude: 139.6503,
        altitude: 10.0,
        accuracy: 5.0,
        altitudeAccuracy: 3.0,
        heading: 0,
        speed: 0,
      },
      timestamp: Date.now(),
    })
  ),
  watchPosition: jest.fn(() => 1),
  clearWatch: jest.fn(),
  requestAuthorization: jest.fn(),
}));

// ─────────────────────────────── react-native-permissions ────────────────────
jest.mock('react-native-permissions', () => ({
  PERMISSIONS: {
    IOS: { CAMERA: 'ios.permission.CAMERA', LOCATION_WHEN_IN_USE: 'ios.permission.LOCATION_WHEN_IN_USE' },
    ANDROID: { CAMERA: 'android.permission.CAMERA', ACCESS_FINE_LOCATION: 'android.permission.ACCESS_FINE_LOCATION' },
  },
  RESULTS: {
    GRANTED: 'granted',
    DENIED: 'denied',
    BLOCKED: 'blocked',
    UNAVAILABLE: 'unavailable',
  },
  request: jest.fn(() => Promise.resolve('granted')),
  check: jest.fn(() => Promise.resolve('granted')),
}));
