/**
 * Axios instance for SignReader API communication.
 * Base URL defaults to localhost:8000 for local development.
 * Override API_BASE_URL at build time for staging/production.
 */
import axios, { AxiosError, AxiosInstance, AxiosResponse } from 'axios';

// 実機: Mac と同じ WiFi に接続している場合は Mac のローカルIP を使用
// Android エミュレーター: 10.0.2.2:8000
// iOS シミュレーター: localhost:8000
export const API_BASE_URL =
  (typeof process !== 'undefined' && process.env?.API_BASE_URL) ||
  'http://192.168.11.128:8000';

export const API_TIMEOUT_MS = 10_000;

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// ─────────────────────────────── Request interceptor ─────────────────────────
apiClient.interceptors.request.use(
  (config) => {
    // Attach auth token here in future when authentication is added
    return config;
  },
  (error: AxiosError) => Promise.reject(error),
);

// ─────────────────────────────── Response interceptor ────────────────────────
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    if (error.response) {
      const status = error.response.status;
      const detail =
        (error.response.data as { detail?: string })?.detail ?? error.message;

      switch (status) {
        case 400:
          return Promise.reject(new Error(`Bad request: ${detail}`));
        case 404:
          return Promise.reject(new Error(`Not found: ${detail}`));
        case 422:
          return Promise.reject(new Error(`Validation error: ${detail}`));
        case 500:
          return Promise.reject(new Error(`Server error: ${detail}`));
        default:
          return Promise.reject(new Error(`Request failed (${status}): ${detail}`));
      }
    }

    if (error.request) {
      return Promise.reject(
        new Error('Network error: no response received from server'),
      );
    }

    return Promise.reject(error);
  },
);

export default apiClient;
