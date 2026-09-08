/**
 * Centralized API configuration.
 * Uses VITE_API_BASE_URL in production (e.g. on Vercel),
 * defaulting to http://127.0.0.1:8000 for local development.
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
