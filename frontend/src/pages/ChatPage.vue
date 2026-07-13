<template>
  <div class="chat-page">
    <!-- 顶部：当前会话标题 -->
    <div class="chat-header">
      <span class="chat-header-icon"></span>
      <span class="chat-header-title">{{ activeConvTitle }}</span>
      <span
        v-if="chatStore.activeConvId && chatStore.messages.length > 0"
        class="chat-header-badge"
      >{{ chatStore.messages.length }} 条消息</span>
    </div>

    <!-- 消息区 -->
    <div class="chat-messages" ref="msgBox">
      <!-- 空状态 -->
      <div v-if="!chatStore.activeConvId && chatStore.messages.length === 0 && !chatStore.sending" class="msg-welcome">
        <div class="welcome-icon"></div>
        <h3>欢迎来到树洞</h3>
        <p>在这里，你可以放心地说出任何心事</p>
        <p class="welcome-hint">点击左侧 <strong>＋</strong> 创建新对话，或选择一个已有会话开始聊天</p>
      </div>

      <!-- 已有会话但无消息 -->
      <div v-else-if="chatStore.activeConvId && chatStore.messages.length === 0 && !chatStore.sending" class="msg-welcome">
        <div class="welcome-icon"></div>
        <p>和树洞说点什么吧~</p>
      </div>

      <!-- 消息列表 -->
      <div
        v-for="m in chatStore.messages"
        :key="m.id"
        class="msg-row"
        :class="'msg-' + m.role"
      >
        <div class="msg-bubble" :class="m.role">
          <div class="msg-text">{{ m.content }}</div>
          <div class="msg-meta" v-if="m.emotion_label">
            <span class="emotion-tag" :class="'emotion-' + m.emotion_label">{{ emotionEmoji[m.emotion_label] || '' }} {{ emotionLabelMap[m.emotion_label] || m.emotion_label }}</span>
          </div>
        </div>
      </div>

      <!-- 发送中加载动画 -->
      <div v-if="chatStore.sending" class="msg-row msg-assistant">
        <div class="msg-bubble assistant">
          <span class="typing-dots"><i></i><i></i><i></i></span>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="chat-input-bar">
      <input
        v-model="inputText"
        @keydown.enter="handleSend"
        class="chat-input"
        placeholder="和树洞说说心里话..."
        :disabled="chatStore.sending"
        ref="inputRef"
      />
      <button
        class="chat-send-btn"
        @click="handleSend"
        :disabled="chatStore.sending || !inputText.trim()"
      >发送</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useChatStore } from '../stores/chat.js'

const chatStore = useChatStore()
const inputText = ref('')
const msgBox = ref(null)
const inputRef = ref(null)

// ── 情感标签映射 ──
const emotionEmoji = {
  joy: '😊', sadness: '😢', anger: '😠', fear: '😨', neutral: '😐',
}
const emotionLabelMap = {
  joy: '开心', sadness: '悲伤', anger: '生气', fear: '害怕', neutral: '平静',
}

// ── 会话标题 ──
const activeConvTitle = computed(() => {
  const c = chatStore.conversations.find(c => c.id === chatStore.activeConvId)
  return c ? c.title : (chatStore.activeConvId ? '对话中' : '新对话')
})

// ── 滚动 ──
function scrollBottom() {
  nextTick(() => {
    if (msgBox.value) {
      msgBox.value.scrollTop = msgBox.value.scrollHeight
    }
  })
}

function focusInput() {
  nextTick(() => inputRef.value?.focus())
}

// 监听消息变化自动滚动
watch(() => chatStore.messages.length, scrollBottom)

// ── 发送 ──
async function handleSend() {
  const text = inputText.value.trim()
  if (!text || chatStore.sending) return
  inputText.value = ''
  try {
    await chatStore.send(text)
    scrollBottom()
  } catch {
    // 错误已在 store 中处理（添加错误消息）
    scrollBottom()
  }
  focusInput()
}

// ── 初始化 ──
onMounted(async () => {
  await chatStore.loadConversations()
  // 默认选中第一个会话或创建新会话
  if (chatStore.conversations.length > 0) {
    await chatStore.selectConv(chatStore.conversations[0].id)
  }
  scrollBottom()
  focusInput()
})
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fafafa;
}

/* ── 头部 ── */
.chat-header {
  padding: 14px 24px;
  background: #fff;
  border-bottom: 1px solid #eee;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.chat-header-icon {
  font-size: 18px;
}
.chat-header-title {
  font-size: 16px;
  font-weight: 600;
  color: #2c3e50;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chat-header-badge {
  font-size: 12px;
  color: #95a5a6;
  background: #f0f2f5;
  padding: 3px 10px;
  border-radius: 12px;
}

/* ── 消息区 ── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 欢迎状态 */
.msg-welcome {
  text-align: center;
  color: #95a5a6;
  margin-top: 80px;
}
.welcome-icon {
  font-size: 56px;
  margin-bottom: 12px;
}
.msg-welcome h3 {
  font-size: 20px;
  color: #555;
  margin-bottom: 8px;
}
.msg-welcome p {
  font-size: 14px;
  margin-bottom: 4px;
}
.welcome-hint {
  color: #bbb;
  font-size: 13px !important;
  margin-top: 12px !important;
}

/* 消息行 */
.msg-row {
  display: flex;
  max-width: 100%;
}
.msg-user {
  justify-content: flex-end;
}
.msg-assistant {
  justify-content: flex-start;
}

/* 消息气泡 */
.msg-bubble {
  max-width: 72%;
  padding: 10px 16px;
  border-radius: 16px;
  font-size: 15px;
  line-height: 1.7;
}
.msg-bubble.user {
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.msg-bubble.assistant {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-bottom-left-radius: 4px;
  color: #333;
}

.msg-text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* 情感标签 */
.msg-meta {
  margin-top: 6px;
  display: flex;
  gap: 6px;
}
.emotion-tag {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(0,0,0,.06);
  color: #888;
}
.emotion-joy { background: #e8f8e8; color: #27ae60; }
.emotion-sadness { background: #e8f0f8; color: #2980b9; }
.emotion-anger { background: #fde8e8; color: #e74c3c; }
.emotion-fear { background: #fef3e8; color: #e67e22; }
.emotion-neutral { background: #f0f0f0; color: #888; }

/* ── 输入区 ── */
.chat-input-bar {
  padding: 14px 24px;
  background: #fff;
  border-top: 1px solid #eee;
  display: flex;
  gap: 10px;
  align-items: center;
  flex-shrink: 0;
}
.chat-input {
  flex: 1;
  padding: 10px 18px;
  border: 1.5px solid #e0e0e0;
  border-radius: 24px;
  font-size: 15px;
  outline: none;
  transition: border .2s;
  background: #fafafa;
}
.chat-input:focus {
  border-color: #667eea;
  background: #fff;
}
.chat-input:disabled {
  opacity: .5;
}
.chat-send-btn {
  padding: 10px 26px;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: #fff;
  border: none;
  border-radius: 24px;
  font-size: 15px;
  cursor: pointer;
  transition: all .2s;
  flex-shrink: 0;
}
.chat-send-btn:hover {
  opacity: .9;
  transform: translateY(-1px);
}
.chat-send-btn:disabled {
  opacity: .4;
  cursor: not-allowed;
  transform: none;
}

/* ── 打字动画 ── */
.typing-dots {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 2px 0;
}
.typing-dots i {
  width: 7px;
  height: 7px;
  background: #667eea;
  border-radius: 50%;
  animation: bounce 1.2s infinite;
}
.typing-dots i:nth-child(2) { animation-delay: .2s; }
.typing-dots i:nth-child(3) { animation-delay: .4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}
</style>
