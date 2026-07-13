const BASE = '/api'

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
  }
  if (body) opts.body = JSON.stringify(body)
  const res = await fetch(BASE + path, opts)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '请求失败')
  return data
}

export const api = {
  // 认证
  register: (username, password) =>
    request('POST', '/auth/register', { username, password }),

  login: (username, password) =>
    request('POST', '/auth/login', { username, password }),

  me: () => request('GET', '/auth/me'),

  // 聊天
  sendMessage: (message, conversationId) =>
    request('POST', '/chat', { message, conversation_id: conversationId }),

  // 会话
  createConversation: (title) =>
    request('POST', '/conversations', { title }),

  listConversations: () => request('GET', '/conversations'),

  getMessages: (conversationId) =>
    request('GET', `/conversations/${conversationId}/messages`),

  updateConversation: (conversationId, title) =>
    request('PATCH', `/conversations/${conversationId}`, { title }),

  // 记忆
  listMemories: (limit = 50) =>
    request('GET', `/memories?limit=${limit}`),

  searchMemories: (query, limit = 5) =>
    request('GET', `/memories/search?q=${encodeURIComponent(query)}&limit=${limit}`),
}
