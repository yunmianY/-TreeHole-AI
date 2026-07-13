<template>
  <div class="memory-page">
    <div class="page-header">
      <h2> 记忆时间线</h2>
      <p class="page-desc">树洞记住的关于你的一切</p>
    </div>

    <div class="memory-content">
      <!-- 情感图表区 -->
      <div v-if="memories.length > 0" class="chart-section">
        <div class="chart-card">
          <h4>情感分布</h4>
          <div ref="pieChartRef" class="chart-box"></div>
        </div>
        <div class="chart-card">
          <h4>记忆时间线</h4>
          <div ref="timelineChartRef" class="chart-box"></div>
        </div>
      </div>

      <!-- 搜索栏 -->
      <div class="search-bar">
        <input
          v-model="searchQuery"
          @keydown.enter="doSearch"
          class="search-input"
          placeholder="搜索记忆..."
        />
        <button class="search-btn" @click="doSearch" :disabled="searching">
          {{ searching ? '搜索中...' : '搜索' }}
        </button>
        <button v-if="isSearching" class="clear-search-btn" @click="clearSearch">清除</button>
      </div>

      <!-- 记忆列表 -->
      <div v-if="loading" class="loading-state">
        <span class="spinner"></span> 加载记忆中...
      </div>
      <div v-else-if="displayMemories.length === 0" class="empty-state">
        <div class="empty-icon"></div>
        <p v-if="isSearching">没有找到相关记忆</p>
        <p v-else>还没有记忆，去和树洞聊聊天吧~</p>
      </div>
      <div v-else class="memory-cards">
        <div
          v-for="m in displayMemories"
          :key="m.id"
          class="memory-card"
          :class="'card-' + (m.emotion_label || 'neutral')"
        >
          <div class="card-header">
            <span class="card-emoji">{{ emotionEmoji[m.emotion_label] || '💭' }}</span>
            <span class="card-label">{{ emotionLabelMap[m.emotion_label] || '其他' }}</span>
            <span class="card-importance">
              <template v-for="i in 5" :key="i">★</template>
            </span>
          </div>
          <p class="card-content">{{ m.content }}</p>
          <div class="card-footer">
            <span class="card-date" v-if="m.created_at">{{ formatDate(m.created_at) }}</span>
            <span class="card-importance-text">重要度: {{ Math.round((m.importance || 0) * 100) }}%</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api/index.js'

// ── 状态 ──
const memories = ref([])
const searchResults = ref(null)
const searchQuery = ref('')
const searching = ref(false)
const loading = ref(true)
const pieChartRef = ref(null)
const timelineChartRef = ref(null)

let pieChart = null
let timelineChart = null

// ── 情感映射 ──
const emotionEmoji = {
  joy: '😊', sadness: '😢', anger: '😠', fear: '😨', neutral: '😐',
}
const emotionLabelMap = {
  joy: '开心', sadness: '悲伤', anger: '生气', fear: '害怕', neutral: '平静',
}
const emotionColors = {
  joy: '#27ae60', sadness: '#2980b9', anger: '#e74c3c', fear: '#e67e22', neutral: '#95a5a6',
}

// ── 计算属性 ──
const isSearching = computed(() => searchResults.value !== null)
const displayMemories = computed(() =>
  isSearching.value ? (searchResults.value || []) : memories.value
)

// ── 日期格式化 ──
function formatDate(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
  } catch { return iso }
}

// ── 搜索 ──
async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) return
  searching.value = true
  try {
    searchResults.value = await api.searchMemories(q, 20)
  } catch (e) {
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

function clearSearch() {
  searchQuery.value = ''
  searchResults.value = null
}

// ── 图表 ──
function renderCharts() {
  nextTick(() => {
    renderPieChart()
    renderTimelineChart()
  })
}

function renderPieChart() {
  if (!pieChartRef.value) return
  if (!pieChart) {
    pieChart = echarts.init(pieChartRef.value)
  }

  // 按情感标签聚合
  const countMap = {}
  memories.value.forEach(m => {
    const label = m.emotion_label || 'neutral'
    countMap[label] = (countMap[label] || 0) + 1
  })

  const data = Object.entries(countMap).map(([label, count]) => ({
    name: emotionLabelMap[label] || label,
    value: count,
    itemStyle: { color: emotionColors[label] || '#95a5a6' },
  }))

  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 条 ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['45%', '75%'],
      center: ['50%', '55%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 16, fontWeight: 'bold' } },
      data,
    }],
  })
}

function renderTimelineChart() {
  if (!timelineChartRef.value) return
  if (!timelineChart) {
    timelineChart = echarts.init(timelineChartRef.value)
  }

  // 按日期聚合记忆数量 + 主导情感
  const dateMap = {}
  const sorted = [...memories.value].sort((a, b) =>
    (a.created_at || '').localeCompare(b.created_at || '')
  )

  sorted.forEach(m => {
    const date = (m.created_at || '').slice(0, 10) || '未知'
    if (!dateMap[date]) dateMap[date] = { count: 0, emotions: {} }
    dateMap[date].count++
    const label = m.emotion_label || 'neutral'
    dateMap[date].emotions[label] = (dateMap[date].emotions[label] || 0) + 1
  })

  const dates = Object.keys(dateMap).sort()
  const counts = dates.map(d => dateMap[d].count)

  timelineChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        if (!params || params.length === 0) return ''
        const d = params[0].axisValue
        const info = dateMap[d]
        const top = Object.entries(info.emotions)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([k, v]) => `${emotionEmoji[k] || ''} ${emotionLabelMap[k] || k}: ${v}`)
          .join('<br/>')
        return `${d}<br/>记忆总数: ${info.count}<br/>${top}`
      },
    },
    grid: { left: 40, right: 16, top: 16, bottom: 24 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { rotate: 45, fontSize: 10, formatter: v => v.slice(5) },
    },
    yAxis: {
      type: 'value',
      name: '记忆数',
      minInterval: 1,
    },
    series: [{
      type: 'bar',
      data: counts,
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#667eea' },
          { offset: 1, color: '#764ba2' },
        ]),
        borderRadius: [6, 6, 0, 0],
      },
    }],
  })
}

// ── 窗口 resize ──
function handleResize() {
  pieChart?.resize()
  timelineChart?.resize()
}

// 监听数据变化重新渲染图表
watch(displayMemories, () => {
  if (!isSearching.value) renderCharts()
})

// ── 初始化 ──
onMounted(async () => {
  try {
    memories.value = await api.listMemories(100)
  } catch {
    memories.value = []
  } finally {
    loading.value = false
    renderCharts()
  }
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  pieChart?.dispose()
  timelineChart?.dispose()
})
</script>

<style scoped>
.memory-page {
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
.memory-content {
  padding: 16px 24px 24px;
}

/* ── 图表 ── */
.chart-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}
.chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.chart-card h4 {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}
.chart-box {
  width: 100%;
  height: 240px;
}

/* ── 搜索 ── */
.search-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.search-input {
  flex: 1;
  padding: 10px 16px;
  border: 1.5px solid #e0e0e0;
  border-radius: 10px;
  font-size: 14px;
  outline: none;
  transition: border .2s;
}
.search-input:focus { border-color: #667eea; }
.search-btn {
  padding: 10px 20px;
  background: #667eea;
  color: #fff;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
}
.search-btn:hover { background: #5a6fd6; }
.search-btn:disabled { opacity: .5; cursor: not-allowed; }
.clear-search-btn {
  padding: 10px 16px;
  background: transparent;
  color: #999;
  border: 1px solid #ddd;
  border-radius: 10px;
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
}
.clear-search-btn:hover { background: #f5f5f5; }

/* ── 空/加载 ── */
.loading-state, .empty-state {
  text-align: center;
  padding: 40px 0;
  color: #95a5a6;
  font-size: 14px;
}
.empty-icon { font-size: 44px; margin-bottom: 8px; }
.spinner {
  display: inline-block;
  width: 16px; height: 16px;
  border: 2px solid #e0e0e0;
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin .6s linear infinite;
  vertical-align: middle;
  margin-right: 6px;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── 记忆卡片 ── */
.memory-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.memory-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  border-left: 4px solid #e0e0e0;
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
  transition: all .15s;
}
.memory-card:hover {
  box-shadow: 0 3px 12px rgba(0,0,0,.08);
  transform: translateY(-1px);
}
.card-joy { border-left-color: #27ae60; }
.card-sadness { border-left-color: #2980b9; }
.card-anger { border-left-color: #e74c3c; }
.card-fear { border-left-color: #e67e22; }
.card-neutral { border-left-color: #bdc3c7; }

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.card-emoji { font-size: 16px; }
.card-label {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #f0f2f5;
  color: #888;
}
.card-importance {
  margin-left: auto;
  font-size: 12px;
  color: #f1c40f;
  letter-spacing: -1px;
}
.card-content {
  font-size: 14px;
  line-height: 1.6;
  color: #333;
  margin-bottom: 8px;
}
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #bbb;
}
.card-importance-text { color: #bbb; }
</style>
