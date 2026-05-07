import axios, { AxiosError, AxiosInstance, AxiosResponse } from 'axios';

export const API_BASE_URL = 'https://api.signreader.amtech-service.com';

export const API_TIMEOUT_MS = 30_000;

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
