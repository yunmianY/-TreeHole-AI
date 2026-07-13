import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/index.js'

export const useChatStore = defineStore('chat', () => {
  // ── state ──
  const conversations = ref([])
  const activeConvId = ref(null)
  const messages = ref([])
  const sending = ref(false)
  const creatingConv = ref(false)
  const initLoading = ref(false)

  // ── actions ──
  async function loadConversations() {
    try {
      conversations.value = await api.listConversations()
    } catch { /* ignore */ }
  }

  async function selectConv(id) {
    activeConvId.value = id
    messages.value = []
    try {
      messages.value = await api.getMessages(id)
    } catch {
      messages.value = []
    }
  }

  async function createConv() {
    if (creatingConv.value) return
    creatingConv.value = true
    try {
      const conv = await api.createConversation('新对话')
      conversations.value.unshift(conv)
      activeConvId.value = conv.id
      messages.value = []
      return conv
    } catch (e) {
      throw e
    } finally {
      creatingConv.value = false
    }
  }

  async function send(text) {
    if (!text || sending.value) return
    sending.value = true

    // 乐观更新用户消息
    messages.value.push({ id: Date.now(), role: 'user', content: text })

    try {
      const res = await api.sendMessage(text, activeConvId.value || null)
      if (!activeConvId.value) {
        activeConvId.value = res.conversation_id
      }
      messages.value.push({ id: res.message_id, role: 'assistant', content: res.content })
      // 后台刷新会话列表（标题可能更新）
      loadConversations()
      return res
    } catch (e) {
      messages.value.push({ id: -Date.now(), role: 'assistant', content: `❌ 发送失败: ${e.message}` })
      throw e
    } finally {
      sending.value = false
    }
  }

  function reset() {
    conversations.value = []
    activeConvId.value = null
    messages.value = []
  }

  async function renameConv(id, newTitle) {
    const conv = conversations.value.find(c => c.id === id)
    if (!conv || !newTitle.trim()) return
    // 乐观更新
    const oldTitle = conv.title
    conv.title = newTitle.trim()
    try {
      await api.updateConversation(id, newTitle.trim())
    } catch {
      // 回滚
      conv.title = oldTitle
      throw new Error('重命名失败')
    }
  }

  return {
    conversations,
    activeConvId,
    messages,
    sending,
    creatingConv,
    initLoading,
    loadConversations,
    selectConv,
    createConv,
    send,
    reset,
    renameConv,
  }
})
