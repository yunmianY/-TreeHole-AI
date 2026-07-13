<template>
  <div class="app-shell">
    <!-- 左侧边栏 -->
    <aside class="sidebar">
      <!-- 品牌 + 用户 -->
      <div class="sidebar-brand">
        <h3>🌳 TreeHole AI</h3>
        <div class="sidebar-user">
          <span class="user-avatar">{{ userStore.user?.username?.charAt(0)?.toUpperCase() || '?' }}</span>
          <span class="user-name">{{ userStore.user?.username || '加载中...' }}</span>
        </div>
      </div>

      <!-- 主导航 -->
      <nav class="sidebar-nav">
        <router-link to="/chat" class="nav-item" active-class="nav-active">
          <span class="nav-icon">💬</span> 聊天
        </router-link>
        <router-link to="/memories" class="nav-item" active-class="nav-active">
          <span class="nav-icon">🧠</span> 记忆时间线
        </router-link>
        <router-link to="/settings" class="nav-item" active-class="nav-active">
          <span class="nav-icon">⚙️</span> 设置
        </router-link>
      </nav>

      <!-- 聊天页专属：会话列表 -->
      <div v-if="route.path === '/chat'" class="sidebar-section">
        <div class="sidebar-section-header">
          <span>会话列表</span>
          <button
            class="sidebar-new-btn"
            @click="handleNewConv"
            :disabled="chatStore.creatingConv"
          >＋</button>
        </div>
        <div class="conv-list">
          <div
            v-for="conv in chatStore.conversations"
            :key="conv.id"
            class="conv-item"
            :class="{ active: chatStore.activeConvId === conv.id, editing: editingId === conv.id }"
            @click="onConvClick(conv.id)"
            @contextmenu.prevent="showContextMenu($event, conv.id)"
          >
            <!-- 编辑中：行内输入框 -->
            <input
              v-if="editingId === conv.id"
              v-model="editTitle"
              class="conv-edit-input"
              @keydown.enter="saveRename(conv.id)"
              @keydown.escape="cancelRename"
              @blur="saveRename(conv.id)"
              @click.stop
              ref="editInputRef"
              maxlength="200"
            />
            <!-- 普通：标题 -->
            <span v-else class="conv-item-title">{{ conv.title }}</span>

            <span class="conv-item-count" v-if="conv.message_count">{{ conv.message_count }}</span>

            <!-- 更多按钮 -->
            <button
              v-if="editingId !== conv.id"
              class="conv-more-btn"
              @click.stop="showContextMenu($event, conv.id)"
              title="更多操作"
            >⋮</button>
          </div>
          <div
            v-if="chatStore.conversations.length === 0 && !chatStore.creatingConv"
            class="conv-empty"
          >
            暂无对话，点击 ＋ 开始
          </div>
        </div>

        <!-- 右键 / 更多菜单 -->
        <Teleport to="body">
          <div
            v-if="menuVisible"
            class="conv-context-menu"
            :style="menuStyle"
            @click.stop
          >
            <button class="menu-item" @click="startRename">✏️ 重命名</button>
          </div>
          <!-- 点击空白关闭菜单 -->
          <div
            v-if="menuVisible"
            class="context-menu-backdrop"
            @click="closeMenu"
          ></div>
        </Teleport>
      </div>

      <!-- 底部：退出 -->
      <div class="sidebar-footer">
        <button class="logout-btn" @click="handleLogout">
          <span>🚪</span> 退出登录
        </button>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../stores/user.js'
import { useChatStore } from '../stores/chat.js'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const chatStore = useChatStore()

// ── 重命名状态 ──
const editingId = ref(null)
const editTitle = ref('')
const editInputRef = ref(null)

// ── 右键菜单状态 ──
const menuVisible = ref(false)
const menuConvId = ref(null)
const menuStyle = reactive({ top: '0px', left: '0px' })

// ── 新建会话 ──
async function handleNewConv() {
  try {
    await chatStore.createConv()
  } catch (e) {
    alert('创建会话失败: ' + e.message)
  }
}

// ── 点击会话项 ──
function onConvClick(id) {
  if (editingId.value === id) return
  closeMenu()
  chatStore.selectConv(id)
}

// ── 右键 / 更多菜单 ──
function showContextMenu(event, convId) {
  menuConvId.value = convId
  // 计算菜单位置（限制不超出视口）
  const x = Math.min(event.clientX, window.innerWidth - 150)
  const y = Math.min(event.clientY, window.innerHeight - 60)
  menuStyle.left = x + 'px'
  menuStyle.top = y + 'px'
  menuVisible.value = true
}

function closeMenu() {
  menuVisible.value = false
  menuConvId.value = null
}

// ── 行内重命名 ──
function startRename() {
  const conv = chatStore.conversations.find(c => c.id === menuConvId.value)
  if (conv) {
    editingId.value = conv.id
    editTitle.value = conv.title
  }
  closeMenu()
  nextTick(() => {
    const inp = editInputRef.value
    if (inp) {
      inp.focus()
      inp.select()
    }
  })
}

async function saveRename(id) {
  if (editingId.value !== id) return
  const newTitle = editTitle.value.trim()
  if (!newTitle) { cancelRename(); return }
  try {
    await chatStore.renameConv(id, newTitle)
  } catch {
    // store 已回滚
  }
  editingId.value = null
}

function cancelRename() {
  editingId.value = null
}

// ── 退出登录 ──
function handleLogout() {
  chatStore.reset()
  userStore.logout()
  router.push('/login')
}

onMounted(async () => {
  if (!userStore.user) {
    try {
      await userStore.fetchUser()
    } catch {
      userStore.logout()
      router.push('/login')
      return
    }
  }
  if (route.path === '/chat') {
    chatStore.loadConversations()
  }
})
</script>

<style scoped>
/* ── 壳层布局 ── */
.app-shell {
  display: flex;
  height: 100vh;
}

/* ── 侧边栏 ── */
.sidebar {
  width: 280px;
  background: #2c3e50;
  color: #ecf0f1;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-brand {
  padding: 20px 16px;
  border-bottom: 1px solid rgba(255,255,255,.1);
}
.sidebar-brand h3 {
  font-size: 17px;
  margin-bottom: 8px;
  color: #fff;
}
.sidebar-user {
  display: flex;
  align-items: center;
  gap: 8px;
}
.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}
.user-name {
  font-size: 13px;
  color: #bdc3c7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 导航 ── */
.sidebar-nav {
  padding: 8px 0;
  border-bottom: 1px solid rgba(255,255,255,.08);
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  color: #bdc3c7;
  text-decoration: none;
  font-size: 14px;
  transition: all .15s;
  border-left: 3px solid transparent;
}
.nav-item:hover {
  background: rgba(255,255,255,.05);
  color: #ecf0f1;
}
.nav-active {
  background: rgba(102,126,234,.2);
  border-left-color: #667eea;
  color: #fff;
}
.nav-icon {
  font-size: 16px;
  width: 22px;
  text-align: center;
}

/* ── 会话列表区 ── */
.sidebar-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  font-size: 12px;
  color: #95a5a6;
  text-transform: uppercase;
  letter-spacing: 1px;
}
.sidebar-new-btn {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: none;
  background: #667eea;
  color: #fff;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background .15s;
}
.sidebar-new-btn:hover {
  background: #5a6fd6;
}
.sidebar-new-btn:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
}
.conv-item {
  padding: 10px 16px;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: all .15s;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.conv-item:hover {
  background: rgba(255,255,255,.06);
}
.conv-item.active {
  background: rgba(102,126,234,.25);
  border-left-color: #667eea;
}
.conv-item-title {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.conv-item-count {
  font-size: 11px;
  color: #95a5a6;
  margin-left: 8px;
  flex-shrink: 0;
  background: rgba(255,255,255,.08);
  padding: 2px 7px;
  border-radius: 10px;
}
.conv-empty {
  padding: 20px 16px;
  color: #7f8c8d;
  font-size: 13px;
  text-align: center;
}

/* 更多按钮 — hover 时显示 */
.conv-more-btn {
  opacity: 0;
  background: none;
  border: none;
  color: #95a5a6;
  cursor: pointer;
  font-size: 16px;
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1;
  flex-shrink: 0;
  margin-left: 4px;
  transition: all .15s;
}
.conv-item:hover .conv-more-btn {
  opacity: 1;
}
.conv-more-btn:hover {
  background: rgba(255,255,255,.12);
  color: #ecf0f1;
}

/* 行内编辑输入框 */
.conv-edit-input {
  flex: 1;
  background: rgba(255,255,255,.12);
  border: 1px solid #667eea;
  border-radius: 6px;
  color: #ecf0f1;
  font-size: 13px;
  padding: 4px 8px;
  outline: none;
  min-width: 0;
}
.conv-edit-input::placeholder {
  color: #7f8c8d;
}

/* 编辑中状态 */
.conv-item.editing {
  background: rgba(102,126,234,.2);
}

/* ── 右键菜单 ── */
.conv-context-menu {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 24px rgba(0,0,0,.18);
  padding: 4px;
  min-width: 130px;
}
.menu-item {
  display: block;
  width: 100%;
  padding: 8px 14px;
  border: none;
  background: none;
  font-size: 13px;
  color: #333;
  cursor: pointer;
  border-radius: 6px;
  text-align: left;
  transition: background .1s;
}
.menu-item:hover {
  background: #f0f2ff;
  color: #667eea;
}

/* 菜单遮罩层（点击关闭） */
.context-menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9998;
}

/* ── 底部 ── */
.sidebar-footer {
  padding: 10px 12px;
  border-top: 1px solid rgba(255,255,255,.1);
}
.logout-btn {
  width: 100%;
  padding: 8px;
  background: transparent;
  color: #e74c3c;
  border: 1px solid rgba(231,76,60,.3);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all .15s;
}
.logout-btn:hover {
  background: rgba(231,76,60,.1);
  border-color: rgba(231,76,60,.5);
}

/* ── 右侧内容 ── */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
}
</style>
