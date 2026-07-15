# AI树洞（个人情感陪伴助手）完整设计方案

## 1. 项目概述

**项目名称**：TreeHole AI —— 你的私人情感树洞

**核心理念**：一个能记住你开心与不开心瞬间的聊天AI，支持多模态交互（文字/图片/语音）、长期记忆、情感追踪、时间线回顾、月度/年度报告等，跨平台使用（微信小程序 + H5 + PWA），数据自主可控，开源可自托管。

**目标用户**：个人使用者，也可分享给好友或开源社区。

---

## 2. 系统架构总览

### 2.1 架构分层图

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层 (UniApp)                       │
│  微信小程序  │  H5网页  │  PWA  │  桌面版（后续）             │
└─────────────────────────────┬───────────────────────────────┘
                              │ HTTPS / WebSocket
┌─────────────────────────────▼───────────────────────────────┐
│                        网关层 (Nginx)                        │
│              反向代理、负载均衡、HTTPS、静态资源               │
└─────────────────────────────┬───────────────────────────────┘
┌─────────────────────────────▼───────────────────────────────┐
│                   应用层 (FastAPI + LangChain)               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ API 路由：/chat /memories /timeline /summary /export  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 核心业务：认证、对话管理、多路检索、记忆提取、情感分析  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ LangChain 组件：LCEL链、记忆、检索器、回调             │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────┬───────────────────┬─────────────────────────┘
                │                   │
┌───────────────▼───────┐   ┌───────▼───────────┐
│      存储层            │   │   外部服务层       │
│ ┌───────────────────┐ │   │ ┌───────────────┐ │
│ │ 关系库 (SQLite/PG) │ │   │ │ 大模型 API    │ │
│ │ • 用户/会话/消息   │ │   │ │ (DeepSeek等)  │ │
│ │ • 记忆节点表       │ │   │ └───────────────┘ │
│ │ • 情感日志         │ │   │ ┌───────────────┐ │
│ └───────────────────┘ │   │ │ 多模态服务     │ │
│ ┌───────────────────┐ │   │ │ (图片/语音)    │ │
│ │ 向量库 (Qdrant)    │ │   │ └───────────────┘ │
│ │ • 语义记忆嵌入     │ │   │ ┌───────────────┐ │
│ └───────────────────┘ │   │ │ 对象存储(OSS)  │ │
│ ┌───────────────────┐ │   │ └───────────────┘ │
│ │ 缓存 (Redis)       │ │   │                   │
│ └───────────────────┘ │   │                   │
└───────────────────────┘   └───────────────────┘
```

### 2.2 技术栈选型

| 层次 | 技术 | 说明 |
|------|------|------|
| 前端 | **UniApp** (Vue3) | 一套代码输出微信小程序、H5、PWA |
| 网关 | **Nginx** 或 **Caddy** | 反向代理，HTTPS，静态文件 |
| 后端框架 | **FastAPI** (Python) | 异步高性能，自动API文档 |
| AI编排 | **LangChain** | 链式调用、记忆管理、检索器 |
| 大模型API | **DeepSeek** / **Qwen** / **Claude** | 对话生成、总结写作、记忆提取 |
| 向量数据库 | **Qdrant** (Docker) | 轻量，开源，支持多路检索 |
| 关系数据库 | **SQLite** (开发) / **PostgreSQL** (生产) | 存储结构化数据 |
| 缓存/会话 | **Redis** | 限流、临时会话、异步任务队列 |
| 对象存储 | **MinIO** 或 云厂商OSS | 多模态文件存储 |
| 部署 | **Docker Compose** | 一键启动所有服务 |
| CI/CD | **GitHub Actions** | 自动化测试、构建镜像 |

---

## 3. 核心模块设计

### 3.1 用户认证与多端同步

- **认证方式**：JWT (Access Token + Refresh Token)
- **登录方式**：支持邮箱/手机号注册登录（初期可简化，仅用户名+密码）
- **多端同步**：同一账号在不同设备登录，聊天记录和记忆实时同步（后端统一存储）
- **安全**：密码bcrypt加密，API通过HTTPS传输

### 3.2 对话引擎（核心）

#### 3.2.1 请求处理流程

1. 前端发送消息（文本/图片/语音）→ 后端认证。
2. **预处理**：图片调用多模态API生成文字描述；语音转文字。
3. **多路检索**（详见3.3）获取相关记忆和历史消息。
4. 构建LangChain `RunnableSequence`，注入：
   - 系统提示词（树洞人设）
   - 检索到的记忆片段（格式化文本）
   - 最近N轮对话历史
5. 调用大模型API，流式生成回复。
6. **后处理**：
   - 存储本轮对话到 `messages` 表。
   - 异步触发“记忆提取”任务（见3.4）。
   - 异步触发“情感分析”打分。
7. 回复通过SSE或WebSocket逐字推送至前端。

#### 3.2.2 上下文窗口管理

- 最近**10轮**对话完整保留（可根据模型上下文长度调整）。
- 超出部分，通过摘要记忆压缩（见3.4）。

### 3.3 多路检索系统（记忆召回）

采用 **RRF (Reciprocal Rank Fusion)** 融合三种检索结果：

| 检索路 | 实现 | 权重/策略 |
|--------|------|-----------|
| **向量语义检索** | Qdrant + `text-embedding-3-small` 或 `bge-m3` | 召回Top-K语义相关记忆（K=5） |
| **关键词检索 (BM25)** | SQLite FTS5 或 PostgreSQL `tsvector` | 从 `memory_nodes` 表content字段检索 |
| **元数据过滤** | 时间范围、情感标签过滤 | 当用户问题中包含“上周”、“开心的事”时启用 |

**融合步骤**：
- 每条检索结果获得RRF分数 = Σ 1/(k + rank_i)，k=60。
- 合并去重后，取Top-3作为注入记忆。

**注入模板示例**：
```
[树洞记忆]
用户之前提到：
- 2026-04-15：因项目上线被表扬，非常开心。
- 2026-04-20：害怕打雷，希望得到安慰。
请温柔地结合这些记忆回复用户。
```

### 3.4 长期记忆系统

#### 3.4.1 记忆类型与存储

| 记忆类型 | 存储介质 | 内容示例 |
|---------|----------|----------|
| **事实记忆** | SQLite `memory_nodes` | “用户生日是5月20日” |
| **情感记忆** | 向量库 + 标签 | “用户因被表扬而喜悦（joy, 0.9）” |
| **事件摘要** | SQLite + 向量 | “用户上周和闺蜜吵架后和好” |
| **用户画像** | SQLite `user_profile` | “喜欢猫，害怕打雷，程序员” |

#### 3.4.2 记忆提取（异步任务）

**触发时机**：每轮对话结束后，作为后台任务（使用FastAPI `BackgroundTasks` 或 Celery）。

**提取模型**：调用轻量大模型（如 `GPT-4o-mini` 或 `Qwen-turbo`），Prompt设计如下：

```
分析以下对话，提取值得长期记忆的信息。输出JSON数组，每个元素包含：
- content: 记忆文本（一句话）
- emotion_label: joy/sadness/anger/fear/neutral
- importance: 0~1 重要度
- related_facts: 相关的事实（如有）

对话：
用户：...
树洞：...
```

提取后计算embedding，存入向量库，同时写入 `memory_nodes` 表。

#### 3.4.3 记忆更新与冲突解决

- 当新记忆与旧记忆矛盾时（如“我以前喜欢猫”→“我现在讨厌猫”），将旧记忆标记为 `deprecated`。
- 采用**重要度合并**：相同语义的记忆只保留一条，更新时间戳和重要度累加。

#### 3.4.4 记忆衰减（可选）

- 为每条记忆设置 `last_accessed`，检索时根据衰减函数降低权重。
- 超过6个月未访问的低重要度记忆，可迁移至冷存储（或删除）。

### 3.5 聊天记录（原始对话）

- **表结构**：`messages` (id, user_id, conversation_id, role, content, timestamp, emotion_score, metadata)
- **索引**：`(user_id, timestamp)` 联合索引，支持时间线快速查询。
- **保留策略**：永久保存（除非用户主动删除）。
- **用途**：精确搜索、时间线阅览、导出备份。

### 3.6 情感分析模块

- **实时打分**：每条用户消息调用 `SnowNLP`（中文）或 `TextBlob`（英文），得到 `emotion_score`（-1~1）和离散标签。
- **存储**：写入 `messages` 表。
- **聚合**：用于时间线情感图、月度/年度报告。

### 3.7 时间线情感变化图

#### 3.7.1 数据聚合API

```
GET /api/timeline/emotion?start=2026-01-01&end=2026-12-31&granularity=week
```

返回每日/周/月的平均情感分、消息总量、主导情绪标签。

#### 3.7.2 前端图表

- 使用 ECharts 绘制**折线图**（日/周粒度）和**热力图日历**（月视图）。
- 交互：点击某一点，跳转到当天的聊天记录列表。

### 3.8 月度与年度总结

#### 3.8.1 内容模块

见之前回答中表格，包含：概览数据、情感轨迹、开心Top3、失落时刻、热门话题、树洞寄语、成长发现等。

#### 3.8.2 生成方式

- **定时任务**：每月1日、每年1月1日自动生成（或用户手动触发）。
- **流程**：
  1. 查询该时间范围内所有消息和记忆。
  2. 统计指标（消息数、活跃天数、情感均值等）。
  3. 从记忆库中提取重要事件（按重要度+情感分排序）。
  4. 调用大模型生成叙事文本（“树洞的话”）。
  5. 存储为 Markdown/HTML，并提供分享/导出功能。

### 3.9 聊天导出与导入

**支持格式**：
- HTML（可读性强，带样式）
- Markdown（简洁）
- JSON（完整数据，便于迁移）

**导出范围**：全部对话、某会话、时间范围、搜索结果（带关键词高亮）。

**隐私保护**：导出文件加密（可选，用户设定密码）。

### 3.10 多模态支持

| 模态 | 输入 | 处理 | 输出 |
|------|------|------|------|
| 图片 | 用户上传 | 调用多模态API（如 `Qwen-VL`）生成文字描述，存入消息content | 树洞可理解图片内容，并记住相关记忆 |
| 语音 | 用户录音 | 调用Whisper或国内语音识别API转文字 | 发送文字给大模型，也可合成语音回复 |
| 输出语音 | 树洞回复 | 调用TTS（如Azure TTS或Edge-TTS）生成语音文件 | 前端播放音频 |

### 3.11 跨平台前端（UniApp）

#### 3.11.1 主要页面

- **聊天页**：对话列表、输入框（支持文字/图片/语音）、消息气泡、流式显示。
- **记忆时间线页**：情感折线图/热力图 + 叙事时间轴。
- **总结报告页**：月度/年度报告卡片，支持生成和分享。
- **聊天记录搜索页**：关键词+时间范围搜索，结果点击跳转上下文。
- **设置页**：账号管理、数据导出/删除、模型切换、主题切换。

#### 3.11.2 状态管理

使用 **Pinia** 管理全局状态：用户信息、当前会话、对话历史缓存、未读消息等。

#### 3.11.3 通信协议

- **普通请求**：HTTP/HTTPS，JSON格式。
- **流式回复**：Fetch API + ReadableStream 或 WebSocket（推荐WebSocket，便于后续扩展主动推送）。

---

## 4. 数据模型设计（核心表）

### 4.1 用户表 `users`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PRIMARY KEY | UUID |
| username | TEXT UNIQUE | |
| hashed_password | TEXT | |
| created_at | TIMESTAMP | |
| settings | JSON | 用户配置（主题、模型偏好等） |

### 4.2 会话表 `conversations`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PRIMARY KEY | UUID |
| user_id | TEXT | FK |
| title | TEXT | 自动生成标题 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### 4.3 消息表 `messages`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 自增 |
| conversation_id | TEXT | FK |
| role | TEXT | 'user' or 'assistant' |
| content | TEXT | 纯文本（图片描述已转换） |
| timestamp | TIMESTAMP | |
| emotion_score | REAL | -1..1 |
| emotion_label | TEXT | joy/sadness/... |
| metadata | JSON | 图片URL、语音URL等 |

### 4.4 记忆节点表 `memories`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PRIMARY KEY | UUID |
| user_id | TEXT | FK |
| content | TEXT | 记忆文本 |
| embedding | BLOB | 可选，向量实际存在向量库 |
| emotion_label | TEXT | |
| importance | REAL | 0~1 |
| source_message_ids | TEXT | JSON数组 |
| created_at | TIMESTAMP | |
| last_accessed | TIMESTAMP | |
| deprecated | BOOLEAN | 默认0 |

### 4.5 情感日志表 `emotion_log`（可选）

| 字段 | 类型 |
|------|------|
| message_id | INTEGER |
| user_id | TEXT |
| timestamp | TIMESTAMP |
| score | REAL |

### 4.6 总结报告表 `summaries`

| 字段 | 类型 |
|------|------|
| id | TEXT |
| user_id | TEXT |
| type | TEXT | 'month', 'year' |
| period_start | DATE |
| period_end | DATE |
| content | TEXT | Markdown或HTML |
| created_at | TIMESTAMP |

---

## 5. API设计（部分核心接口）

### 5.1 聊天接口

**`POST /api/chat/stream`** (WebSocket 或 SSE)

请求体：
```json
{
  "conversation_id": "uuid",
  "message": "我今天好开心",
  "files": ["图片URL"]  // 可选
}
```

响应：流式消息块，最终包含 `message_id`。

### 5.2 记忆检索（调试用）

**`GET /api/memories/search?q=害怕&limit=5`**

### 5.3 时间线情感数据

**`GET /api/timeline/emotion?start=2026-01-01&end=2026-12-31&granularity=week`**

### 5.4 生成总结

**`POST /api/summaries/generate`**

```json
{ "type": "month", "year": 2026, "month": 4 }
```

返回报告ID，异步生成。

### 5.5 聊天记录搜索

**`GET /api/search/messages?q=面试&start_date=2026-04-01&end_date=2026-04-30`**

---

## 6. 部署方案（开源版）

### 6.1 使用 Docker Compose 一键部署

```yaml
version: '3.8'
services:
  nginx:
    image: nginx:alpine
    ports: ["80:80","443:443"]
    volumes: ["./nginx.conf:/etc/nginx/nginx.conf"]
    depends_on: [backend]

  backend:
    build: ./backend
    environment:
      - DATABASE_URL=sqlite:///data/treehole.db
      - QDRANT_HOST=qdrant
      - REDIS_URL=redis://redis:6379
    volumes: ["./data:/app/data"]
    depends_on: [qdrant, redis]

  qdrant:
    image: qdrant/qdrant
    volumes: ["./qdrant_storage:/qdrant/storage"]

  redis:
    image: redis:alpine

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    volumes: ["./minio_data:/data"]
```

### 6.2 环境变量配置

创建 `.env` 文件：
```
LLM_API_KEY=your_key
LLM_BASE_URL=https://api.deepseek.com
EMBEDDING_MODEL=text-embedding-3-small
TTS_API_KEY=...
```

### 6.3 前端构建与部署

- UniApp 编译为 H5：输出到 `dist/h5`，由 Nginx 托管。
- 微信小程序：上传到微信公众平台，后端域名需配置 HTTPS。

