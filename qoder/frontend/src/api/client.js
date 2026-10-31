/** API client for the 知序 backend. */

const BASE = import.meta.env.VITE_API_BASE || '/api';

async function request(path, options = {}) {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  // Knowledge
  listDocuments: () => request('/knowledge/documents'),
  getDocument: (id) => request(`/knowledge/documents/${id}`),
  createDocument: (doc) => request('/knowledge/documents', { method: 'POST', body: JSON.stringify(doc) }),
  deleteDocument: (id) => request(`/knowledge/documents/${id}`, { method: 'DELETE' }),
  search: (q, params = {}) => {
    const qs = new URLSearchParams({ q, ...params }).toString();
    return request(`/knowledge/search?${qs}`);
  },

  // Chat
  sendMessage: (message, userId = 'default', sessionId = 'default') =>
    request('/chat/message', { method: 'POST', body: JSON.stringify({ message, user_id: userId, session_id: sessionId }) }),
  getHistory: (userId) => request(`/chat/history/${userId}`),

  // Review
  getReviewStatus: (userId) => request(`/review/status/${userId}`),
  markMastery: (data) => request('/review/mastery', { method: 'POST', body: JSON.stringify(data) }),
  getLearningMemory: (userId) => request(`/review/memory/${userId}`),

  // Health
  health: () => request('/health'),
};
