<template>
  <div class="settings-page">
    <div class="page-header">
      <h2> 设置</h2>
      <p class="page-desc">账户管理与数据控制</p>
    </div>

    <div class="settings-content">
      <!-- 账户信息卡片 -->
      <section class="settings-section">
        <h4> 账户信息</h4>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">用户名</span>
            <span class="info-value">{{ userStore.user?.username || '-' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">用户 ID</span>
            <span class="info-value mono">{{ userStore.user?.id || '-' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">注册时间</span>
            <span class="info-value">{{ userStore.user?.created_at ? formatDate(userStore.user.created_at) : '-' }}</span>
          </div>
        </div>
      </section>

      <!-- 数据导出 -->
      <section class="settings-section">
        <h4>数据导出</h4>
        <p class="section-desc">将你的聊天记录导出为不同格式的文件，数据完全属于你。</p>
        <div class="export-actions">
          <button class="export-btn html" @click="() => doExport('html')" :disabled="exporting">
            <span class="btn-icon">📄</span>
            <div>
              <strong>导出 HTML</strong>
              <small>可在浏览器中查看，带样式</small>
            </div>
          </button>
          <button class="export-btn md" @click="() => doExport('markdown')" :disabled="exporting">
            <span class="btn-icon"></span>
            <div>
              <strong>导出 Markdown</strong>
              <small>纯文本，适合归档</small>
            </div>
          </button>
          <button class="export-btn json" @click="() => doExport('json')" :disabled="exporting">
            <span class="btn-icon"></span>
            <div>
              <strong>导出 JSON</strong>
              <small>完整数据，便于迁移</small>
            </div>
          </button>
        </div>
        <div v-if="exportMsg" class="export-msg" :class="exportMsgType">{{ exportMsg }}</div>
      </section>

      <!-- 危险操作 -->
      <section class="settings-section danger-section">
        <h4> 危险操作</h4>
        <p class="section-desc">以下操作不可撤销，请谨慎操作。</p>
        <button class="danger-btn" @click="handleDeleteConfirm">
          🗑️ 清空所有聊天数据
        </button>
        <div v-if="showDeleteConfirm" class="delete-confirm">
          <p>确定要删除所有聊天记录和记忆吗？这个操作无法撤销。</p>
          <div class="delete-actions">
            <button class="btn-cancel" @click="showDeleteConfirm = false">取消</button>
            <button class="btn-confirm-delete" @click="handleDeleteAll">确认删除</button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useUserStore } from '../stores/user.js'
import { api } from '../api/index.js'

const userStore = useUserStore()
const exporting = ref(false)
const exportMsg = ref('')
const exportMsgType = ref('success')
const showDeleteConfirm = ref(false)

// ── 日期格式化 ──
function formatDate(iso) {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
  } catch { return iso }
}

// ── 数据导出 ──
function triggerDownload(content, filename, mime) {
  const blob = new Blob(['﻿' + content], { type: mime }) // BOM 确保中文正常
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function doExport(format) {
  exporting.value = true
  exportMsg.value = ''
  try {
    // 获取所有会话
    const conversations = await api.listConversations()

    // 获取所有消息
    const allData = []
    for (const conv of conversations) {
      try {
        const msgs = await api.getMessages(conv.id)
        allData.push({ conversation: conv, messages: msgs })
      } catch { /* skip */ }
    }

    if (allData.length === 0) {
      exportMsg.value = '没有可导出的对话数据'
      exportMsgType.value = 'warning'
      return
    }

    const now = new Date().toISOString().slice(0, 10)

    if (format === 'json') {
      const json = JSON.stringify(allData, null, 2)
      triggerDownload(json, `treehole-export-${now}.json`, 'application/json')
      exportMsg.value = `已导出 ${allData.length} 个会话 (JSON 格式)`
    } else if (format === 'markdown') {
      let md = `# TreeHole AI 聊天记录导出\n\n导出时间：${new Date().toLocaleString('zh-CN')}\n\n---\n\n`
      for (const { conversation, messages } of allData) {
        md += `## ${conversation.title}\n`
        md += `会话 ID：${conversation.id}  |  创建时间：${conversation.created_at}\n\n`
        for (const m of messages) {
          const role = m.role === 'user' ? '你' : '树洞'
          const time = m.timestamp ? new Date(m.timestamp).toLocaleString('zh-CN') : ''
          const emotion = m.emotion_label ? ` [${m.emotion_label}]` : ''
          md += `**${role}**${emotion} _${time}_\n\n${m.content}\n\n---\n\n`
        }
      }
      triggerDownload(md, `treehole-export-${now}.md`, 'text/markdown')
      exportMsg.value = `已导出 ${allData.length} 个会话 (Markdown 格式)`
    } else if (format === 'html') {
      let html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>TreeHole AI 聊天记录</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:800px;margin:40px auto;padding:0 20px;background:#fafafa;color:#333}
h1{color:#667eea}h2{border-bottom:2px solid #667eea;padding-bottom:8px;margin-top:32px;color:#2c3e50}
.msg{margin:16px 0;padding:12px 16px;border-radius:12px;line-height:1.7}
.msg.user{background:#ede9fe;border-left:4px solid #667eea}.msg.assistant{background:#fff;border:1px solid #e8e8e8}
.meta{font-size:12px;color:#999;margin-bottom:4px}.emotion{font-size:12px;padding:2px 6px;border-radius:6px;background:#f0f0f0}
.footer{margin-top:32px;padding-top:16px;border-top:1px solid #eee;font-size:12px;color:#bbb}</style></head><body>
<h1>🌳 TreeHole AI 聊天记录导出</h1><p>导出时间：${new Date().toLocaleString('zh-CN')}</p>`
      for (const { conversation, messages } of allData) {
        html += `<h2>${escapeHtml(conversation.title)}</h2>
<p style="color:#999;font-size:13px">会话 ID：${conversation.id}  |  创建时间：${conversation.created_at || '-'}</p>`
        for (const m of messages) {
          const roleLabel = m.role === 'user' ? '你' : '树洞'
          const time = m.timestamp ? new Date(m.timestamp).toLocaleString('zh-CN') : ''
          const emotion = m.emotion_label ? `<span class="emotion">${m.emotion_label}</span>` : ''
          html += `<div class="msg ${m.role}"><div class="meta">${roleLabel} ${emotion} ${time}</div><div>${escapeHtml(m.content)}</div></div>`
        }
      }
      html += `<div class="footer">由 TreeHole AI 生成 — ${new Date().toISOString()}</div></body></html>`
      triggerDownload(html, `treehole-export-${now}.html`, 'text/html')
      exportMsg.value = `已导出 ${allData.length} 个会话 (HTML 格式，可在浏览器中查看)`
    }
    exportMsgType.value = 'success'
  } catch (e) {
    exportMsg.value = '导出失败: ' + e.message
    exportMsgType.value = 'error'
  } finally {
    exporting.value = false
  }
}

function escapeHtml(text) {
  const d = document.createElement('div')
  d.textContent = text
  return d.innerHTML
}

// ── 删除确认 ──
function handleDeleteConfirm() {
  showDeleteConfirm.value = true
}

async function handleDeleteAll() {
  showDeleteConfirm.value = false
  // 逐个删除会话的消息（后端暂未提供批量删除 API，清空通过每个 conversation 的消息逐条处理）
  // 当前提示用户此功能需要后端配合
  alert('此功能需要后端提供批量删除 API，后续开发中会支持。\n\n你可以通过重新注册一个新账号来清空数据。')
}
</script>

<style scoped>
.settings-page {
  height: 100%;
  overflow-y: auto;
}
.page-header {
  padding: 20px 24px 0;
}
.page-header h2 {
  font-size: 22px;
  color: #2c3e50;
  margin-bottom: 4px;
}
.page-desc {
  font-size: 13px;
  color: #95a5a6;
}
.settings-content {
  padding: 16px 24px 32px;
  max-width: 600px;
}

/* ── Section ── */
.settings-section {
  margin-bottom: 24px;
}
.settings-section h4 {
  font-size: 16px;
  color: #2c3e50;
  margin-bottom: 10px;
}
.section-desc {
  font-size: 13px;
  color: #95a5a6;
  margin-bottom: 12px;
}

/* ── 账户信息 ── */
.info-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
}
.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #f5f5f5;
}
.info-row:last-child { border-bottom: none; }
.info-label { font-size: 14px; color: #888; }
.info-value { font-size: 14px; color: #333; font-weight: 500; }
.mono { font-family: monospace; font-size: 12px; color: #667eea; word-break: break-all; }

/* ── 导出按钮 ── */
.export-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.export-btn {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  background: #fff;
  border: 1.5px solid #e8e8e8;
  border-radius: 12px;
  cursor: pointer;
  text-align: left;
  transition: all .15s;
}
.export-btn:hover {
  border-color: #667eea;
  box-shadow: 0 2px 8px rgba(102,126,234,.1);
}
.export-btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-icon { font-size: 28px; flex-shrink: 0; }
.export-btn strong { display: block; font-size: 14px; color: #333; margin-bottom: 2px; }
.export-btn small { font-size: 12px; color: #999; }
.export-msg {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
}
.export-msg.success { background: #e8f8e8; color: #27ae60; }
.export-msg.warning { background: #fef9e7; color: #e67e22; }
.export-msg.error { background: #fde8e8; color: #e74c3c; }

/* ── 危险操作 ── */
.danger-section {
  border: 1px solid #fde8e8;
  border-radius: 12px;
  padding: 16px 20px;
  background: #fffbfb;
}
.danger-btn {
  padding: 10px 20px;
  background: #fff;
  border: 1.5px solid #e74c3c;
  color: #e74c3c;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all .15s;
}
.danger-btn:hover { background: #fde8e8; }
.delete-confirm {
  margin-top: 12px;
  padding: 12px;
  background: #fff5f5;
  border-radius: 8px;
  font-size: 13px;
  color: #c0392b;
}
.delete-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.btn-cancel {
  padding: 6px 16px;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.btn-confirm-delete {
  padding: 6px 16px;
  background: #e74c3c;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
</style>
