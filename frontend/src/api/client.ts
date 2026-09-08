/**
 * src/api/client.ts
 * Centralized Axios instance for the AyaskX API.
 * All requests go through this client.
 */

import axios from 'axios';

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// Response interceptor — unwrap envelope or throw structured error
apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    const message: string =
      err?.response?.data?.errors?.[0] ??
      err?.response?.data?.detail ??
      err?.message ??
      'Unknown error';
    return Promise.reject(new Error(message));
  }
);
