# TreeHole AI — 代码与数据库文档

> 版本：V0.2　|　更新日期：2026-06-01

---

## 目录

- [1. 项目总览](#1-项目总览)
- [2. 目录结构](#2-目录结构)
- [3. 分层架构](#3-分层架构)
- [4. 代码文件说明](#4-代码文件说明)
  - [4.1 入口层 — main.py](#41-入口层)
  - [4.2 基础设施层 — core/](#42-基础设施层)
  - [4.3 数据模型层 — models/](#43-数据模型层)
  - [4.4 数据校验层 — schemas/](#44-数据校验层)
  - [4.5 业务服务层 — services/](#45-业务服务层)
  - [4.6 路由层 — api/](#46-路由层)
- [5. 数据库表设计](#5-数据库表设计)
- [6. API 接口一览](#6-api-接口一览)
- [7. 对话处理完整流程](#7-对话处理完整流程)
- [8. 可扩展性设计](#8-可扩展性设计)

---

## 1. 项目总览

**TreeHole AI**（AI树洞）是一个具有长期记忆能力的中文情感陪伴聊天助手。用户可以随时向树洞倾诉，树洞会记住用户的喜怒哀乐，在后续对话中自然引用记忆，让用户感受到"被记住"和"被在乎"。

### 核心能力

| 版本 | 能力 |
|------|------|
| V0.1 | 多轮对话、JWT 认证、会话管理 |
| V0.2 | 长期记忆提取与召回、多路检索(RRF)、情感分析、异步记忆处理 |

---

## 2. 目录结构

```
backend/
├── .env                          # 环境变量配置（API Key、数据库URL等）
├── .env.example                  # 配置模板
├── requirements.txt              # Python 依赖
├── test_api.py                   # 端到端测试脚本
├── data/                         # 运行时数据（自动生成）
│   ├── treehole.db               # SQLite 数据库
│   └── chroma/                   # ChromaDB 向量存储
└── app/
    ├── __init__.py
    ├── main.py                   # FastAPI 入口：启动、CORS、路由注册
    ├── core/                     # 基础设施层
    │   ├── config.py             # 全局配置（环境变量 → pydantic Settings）
    │   ├── database.py           # SQLAlchemy 引擎 + 会话工厂
    │   └── security.py           # bcrypt 密码哈希 + JWT
    ├── models/                   # ORM 数据模型
    │   ├── user.py               # users 表
    │   ├── conversation.py       # conversations 表
    │   ├── message.py            # messages 表
    │   └── memory.py             # memories 表 + FTS5 全文索引
    ├── schemas/                  # 请求/响应 Pydantic 模型
    │   ├── user.py               # 注册/登录/用户信息
    │   ├── chat.py               # 聊天请求/响应
    │   ├── conversation.py       # 会话/消息记录
    │   └── memory.py             # 记忆检索/列表
    ├── services/                 # 业务逻辑服务
    │   ├── base.py               # LLMProvider 抽象基类
    │   ├── deepseek_provider.py  # DeepSeek 大模型实现
    │   ├── chat_service.py       # 对话编排（核心管道）
    │   ├── auth_service.py       # 注册/登录业务
    │   ├── memory_service.py     # 记忆提取 + 多路检索(RRF) + 去重
    │   ├── emotion_service.py    # LLM 情感分析（打分+标签）
    │   ├── embedding_service.py  # 文本向量化（TF-IDF / SentenceTransformer）
    │   └── vector_store.py       # 向量存储（ChromaDB）
    └── api/                      # HTTP 路由
        ├── deps.py               # 依赖注入（get_db, get_current_user）
        ├── auth.py               # /api/auth/*
        ├── chat.py               # /api/chat
        ├── conversation.py       # /api/conversations/*
        └── memory.py             # /api/memories/*
```

---

## 3. 分层架构

```
┌─────────────────────────────────────────────┐
│  api/        HTTP 路由层                     │
│             解析请求 → 调用服务 → 返回响应     │
├─────────────────────────────────────────────┤
│  schemas/    数据校验层                      │
│             Pydantic 模型，请求体/响应体定义   │
├─────────────────────────────────────────────┤
│  services/   业务逻辑层                       │
│             对话编排、记忆提取、情感分析、认证   │
├─────────────────────────────────────────────┤
│  models/     数据模型层                       │
│             SQLAlchemy ORM，映射数据库表       │
├─────────────────────────────────────────────┤
│  core/       基础设施层                       │
│             配置、数据库连接、JWT、密码哈希     │
└─────────────────────────────────────────────┘
```

**数据流方向**：`api → schemas → services → models → core/database`

---

## 4. 代码文件说明

### 4.1 入口层

#### `app/main.py` — 应用启动入口

| 项目 | 说明 |
|------|------|
| **功能** | FastAPI 应用创建、CORS 中间件、路由注册、自动建表 |
| **lifespan** | 启动时执行 `Base.metadata.create_all()` 自动创建所有数据库表 |
| **CORS** | 开发阶段 `allow_origins=["*"]`，生产环境应限制 |
| **路由** | 注册 auth / chat / conversation / memory 四个子路由 |
| **启动** | `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |

---

### 4.2 基础设施层

#### `app/core/config.py` — 全局配置

| 项目 | 说明 |
|------|------|
| **功能** | 集中管理所有可配置项，通过 `.env` 文件或环境变量注入 |
| **关键类** | `Settings(pydantic_settings.BaseSettings)` |
| **LLM 配置** | `llm_api_key`, `llm_base_url`, `llm_model` — 大模型连接参数 |
| **JWT 配置** | `secret_key`, `algorithm`, `access_token_expire_minutes` |
| **数据库配置** | `database_url` — 支持 SQLite/PostgreSQL/MySQL |
| **路径解析** | `resolved_database_url` 属性将 SQLite 相对路径转为绝对路径，确保从任何目录启动都能正确找到数据库文件 |

#### `app/core/database.py` — 数据库引擎

| 项目 | 说明 |
|------|------|
| **功能** | 创建 SQLAlchemy 引擎与会话工厂 |
| **engine** | `create_engine(settings.resolved_database_url)` — SQLite 自动启用 `check_same_thread=False` |
| **SessionLocal** | `sessionmaker` 会话工厂，每个请求独立会话 |
| **Base** | `declarative_base()` — 所有 ORM 模型的基类 |
| **get_db()** | FastAPI 依赖注入函数，`yield` 会话，请求结束后自动关闭 |

#### `app/core/security.py` — 密码与令牌

| 函数 | 功能 |
|------|------|
| `hash_password(plain) → str` | bcrypt 加盐哈希（限制 72 字节输入） |
| `verify_password(plain, hashed) → bool` | 验证明文密码与哈希匹配 |
| `create_access_token(data, expires_delta) → str` | 创建 JWT token，包含 `sub`(user_id) 和 `exp`(过期时间) |
| `decode_access_token(token) → dict\|None` | 解码 JWT，无效或过期返回 None |

---

### 4.3 数据模型层

#### `app/models/user.py` — 用户表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | UUID，自动生成 |
| `username` | TEXT UNIQUE | 用户名，建立索引 |
| `hashed_password` | TEXT | bcrypt 哈希后的密码 |
| `created_at` | DATETIME | 注册时间 |
| `settings` | JSON | 用户偏好设置（预留） |

**关系**：`User.conversations` → 一对多关联到 `Conversation`

#### `app/models/conversation.py` — 会话表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | UUID |
| `user_id` | TEXT FK | 外键 → users.id |
| `title` | TEXT | 会话标题，默认"新对话"，首条消息后自动截取 |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 最后更新时间，自动更新 |

**关系**：`Conversation.messages` → 一对多关联到 `Message`

#### `app/models/message.py` — 消息表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `conversation_id` | TEXT FK | 外键 → conversations.id |
| `role` | TEXT | `user` / `assistant` |
| `content` | TEXT | 消息内容 |
| `timestamp` | DATETIME | 发送时间，建立索引 |
| `emotion_score` | FLOAT | 情感分值 -1~1（V0.2 自动填充） |
| `emotion_label` | TEXT | 情感标签 joy/sadness/anger/fear/neutral |
| `metadata` | JSON | 扩展字段（图片URL、语音URL等，预留） |

#### `app/models/memory.py` — 记忆节点表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | UUID |
| `user_id` | TEXT | 用户 ID，建立索引 |
| `content` | TEXT | 记忆文本（一句话概括） |
| `emotion_label` | TEXT | 关联的情感标签 |
| `importance` | FLOAT | 重要度 0~1 |
| `source_message_ids` | JSON | 来源消息 ID 列表 |
| `created_at` | DATETIME | 创建时间 |
| `last_accessed` | DATETIME | 最后访问时间（记忆衰减用） |
| `deprecated` | BOOLEAN | 是否已废弃（冲突去重时标记） |

**FTS5 全文索引**：
- 自动创建虚拟表 `memories_fts`，使用 `content` 字段建全文索引
- 3 个触发器（INSERT/UPDATE/DELETE）自动保持 FTS5 索引与 memories 表同步
- 支持中英文混合搜索，FTS5 MATCH 失败时自动回退到 LIKE 模糊匹配

---

### 4.4 数据校验层

#### `app/schemas/user.py`

| 模型 | 用途 |
|------|------|
| `UserRegisterRequest` | 注册请求体：username(2-50字), password(6-128字) |
| `UserLoginRequest` | 登录请求体：username, password |
| `TokenResponse` | Token 响应：access_token + token_type("bearer") |
| `UserResponse` | 用户信息响应：id, username, created_at |

#### `app/schemas/chat.py`

| 模型 | 用途 |
|------|------|
| `ChatRequest` | 聊天请求：message(必填), conversation_id(可选), streaming(预留) |
| `ChatResponse` | 聊天响应：message_id, conversation_id, role, content |

#### `app/schemas/conversation.py`

| 模型 | 用途 |
|------|------|
| `ConversationCreateRequest` | 创建会话请求：title(可选) |
| `ConversationResponse` | 会话列表项：id, title, created_at, updated_at, message_count |
| `MessageInConversation` | 消息历史项：id, role, content, timestamp, emotion_score, emotion_label |

#### `app/schemas/memory.py`

| 模型 | 用途 |
|------|------|
| `MemorySearchRequest` | 记忆搜索请求：query, limit |
| `MemoryItem` | 记忆响应：id, content, emotion_label, importance, created_at |

---

### 4.5 业务服务层

#### `app/services/base.py` — LLM 抽象基类

| 项目 | 说明 |
|------|------|
| **类** | `LLMProvider(ABC)` |
| **抽象方法** | `chat(messages: list[dict], **kwargs) → str` |
| **扩展方式** | 继承 `LLMProvider` → 实现 `chat()` → 在 `config.py` 添加配置 |

**设计意图**：将大模型调用与具体实现解耦，方便在 DeepSeek / Qwen / Claude 之间切换，也方便单元测试时 mock。

#### `app/services/deepseek_provider.py` — DeepSeek 实现

| 项目 | 说明 |
|------|------|
| **类** | `DeepSeekProvider(LLMProvider)` |
| **底层** | 基于 `langchain_openai.ChatOpenAI`（DeepSeek 兼容 OpenAI API） |
| **延迟初始化** | `_get_client()` 在首次 `chat()` 调用时创建客户端，避免模块导入时的配置加载顺序问题 |
| **消息转换** | 将 dict 格式消息（`{"role":"user","content":"..."}`）转为 LangChain 的 `HumanMessage`/`SystemMessage`/`AIMessage` |
| **参数支持** | `temperature`、`max_tokens` 可通过 `**kwargs` 运行时覆盖 |

#### `app/services/chat_service.py` — 对话编排（核心）

| 项目 | 说明 |
|------|------|
| **类** | `ChatService` |
| **职责** | 将对话处理分解为 9 个管道阶段，每个阶段职责单一 |

**管道流程**：

```
阶段1: get_or_create_conversation  →  解析或创建会话
阶段2: load_recent_messages        →  加载最近 20 条历史消息
阶段3: retrieve_memories           →  多路检索用户记忆（V0.2）
阶段4: save_user_msg              →  持久化用户消息
阶段5: analyze_and_update_emotion →  LLM 情感分析，更新 message 行（V0.2）
阶段6: call_llm                    →  调用大模型生成回复
阶段7: save_asst_msg              →  持久化助手回复
阶段8: trigger_memory_extraction  →  暂存上下文供后台提取记忆（V0.2）
阶段9: update_conversation_meta   →  更新会话标题和时间戳
```

**关键设计**：
- `SYSTEM_PROMPT`：树洞人设提示词（温暖、善解人意、有安全底线）
- `MEMORY_CONTEXT_TEMPLATE`：记忆注入模板，将检索到的记忆格式化后嵌入 system prompt
- `pop_extraction_context()`：主线程和后台线程之间的通信桥梁，api 层取走上下文后交给 BackgroundTasks
- `extract_memories_sync()`：供后台线程调用的记忆提取入口

#### `app/services/memory_service.py` — 记忆系统

| 项目 | 说明 |
|------|------|
| **类** | `MemoryService` |
| **依赖** | `LLMProvider` + `EmbeddingProvider` + `VectorStore` |

**三个核心方法**：

| 方法 | 功能 |
|------|------|
| `extract_memories(db, user_id, messages) → int` | LLM 分析对话 → 提取 JSON 记忆列表 → 计算 embedding → 写入关系库 + 向量库 → 语义去重 |
| `retrieve(db, user_id, query, top_k) → list[dict]` | 多路检索（向量 + FTS5 关键词） → RRF 融合 → 返回 Top-K |
| `_rrf_fuse(vector, keyword, top_k)` | Reciprocal Rank Fusion：`score = Σ 1/(60 + rank_i)` |

**记忆提取 Prompt**：要求 LLM 提取最多 5 条记忆，每条含 content / emotion_label / importance。只提取长期信息，跳过临时闲聊。

**语义去重**：新记忆向量在 ChromaDB 中搜索，相似度 > 0.85 视为重复，跳过不存储。

#### `app/services/emotion_service.py` — 情感分析

| 项目 | 说明 |
|------|------|
| **类** | `EmotionService` |
| **方法** | `analyze(message: str) → {"score": float, "label": str}` |
| **原理** | 向 LLM 发送专用 prompt，要求返回 JSON `{"score":-1~1, "label":"joy/sadness/..."}` |

**解析容错**：三层回退机制
1. `json.loads()` 直接解析
2. 正则提取 `{...}` JSON 对象
3. 正则直接提取数字 + 关键词匹配

#### `app/services/embedding_service.py` — 文本向量化

| 类 | 说明 |
|------|------|
| `EmbeddingProvider(ABC)` | 抽象接口：`embed(text) → list[float]`, `embed_batch(texts) → list[list[float]]` |
| `TFIDFEmbeddingProvider` | **[当前默认]** 基于 sklearn `TfidfVectorizer`，字符级 2-4 gram，256 维，完全离线，自动拟合语料库 |
| `SentenceTransformersProvider` | **[可选]** 基于 `paraphrase-multilingual-MiniLM-L12-v2`，384 维，需下载模型 |

**切换方式**：将 `api/chat.py` 和 `api/memory.py` 中的 `TFIDFEmbeddingProvider` 替换为 `SentenceTransformersProvider`

#### `app/services/vector_store.py` — 向量存储

| 类 | 说明 |
|------|------|
| `VectorStore(ABC)` | 抽象接口：`add`, `search`, `delete`, `count` |
| `ChromaDBStore` | **[当前实现]** 基于 ChromaDB 持久化客户端，每个用户独立 collection（`memories_{user_id}`），数据存于 `data/chroma/` |

**切换方式**：实现 `VectorStore` 子类（如 QdrantStore），在 api 层替换注入。

#### `app/services/auth_service.py` — 认证服务

| 方法 | 功能 |
|------|------|
| `register(db, username, password) → (User\|None, error\|None)` | 检查用户名唯一性 → bcrypt 哈希密码 → 创建用户 |
| `login(db, username, password) → (token\|None, error\|None)` | 查询用户 → 验证密码 → 生成 JWT |
| `get_user_by_id(db, user_id) → User\|None` | 按 ID 查找用户 |

---

### 4.6 路由层

#### `app/api/deps.py` — 依赖注入

| 函数 | 功能 |
|------|------|
| `get_db() → Session` | 提供数据库会话，请求结束自动关闭 |
| `get_current_user(credentials, db) → User` | 从 Authorization Header 提取 Bearer Token → 解码 JWT → 查询用户 → 返回 User 对象或 401 |

#### `app/api/auth.py` — 认证路由

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/auth/register` | POST | 注册新用户（201），用户名重复返回 409 |
| `/api/auth/login` | POST | 登录，返回 JWT access_token |
| `/api/auth/me` | GET | 获取当前用户信息（需 Bearer Token） |

#### `app/api/chat.py` — 聊天路由

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/chat` | POST | 发送消息给树洞，返回 AI 回复 |

**内部流程**：
1. 调用 `ChatService.send_message()` 执行 9 阶段管道
2. 通过 `pop_extraction_context()` 取出待处理上下文
3. `BackgroundTasks.add_task()` 将记忆提取加入后台任务（不阻塞回复）

**服务初始化**：模块级创建所有单例，LLM → EmotionService → MemoryService(LLM + TF-IDF + ChromaDB) → ChatService

#### `app/api/conversation.py` — 会话路由

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/conversations` | POST | 创建新会话 |
| `/api/conversations` | GET | 获取会话列表（按更新时间倒序，含消息计数） |
| `/api/conversations/{id}/messages` | GET | 获取会话的消息历史（含情感标签） |

#### `app/api/memory.py` — 记忆路由

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/memories` | GET | 列出用户所有记忆（按创建时间倒序，最多 100 条） |
| `/api/memories/search?q=xxx&limit=5` | GET | 多路检索记忆（向量 + 关键词 + RRF 融合） |

---

## 5. 数据库表设计

### 整体 ER 关系

```
users (1) ─────< (N) conversations (1) ─────< (N) messages
  │
  └──────────────< (N) memories
  │
  └── memories_fts (FTS5 虚拟表，自动同步)
```

### 5.1 users — 用户表

| # | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|
| 1 | id | TEXT | PK, UUID | 用户唯一标识 |
| 2 | username | TEXT | UNIQUE, NOT NULL, INDEX | 用户名 |
| 3 | hashed_password | TEXT | NOT NULL | bcrypt 哈希密码 |
| 4 | created_at | DATETIME | | 注册时间 |
| 5 | settings | JSON | | 用户配置（主题、模型偏好等） |

### 5.2 conversations — 会话表

| # | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|
| 1 | id | TEXT | PK, UUID | 会话唯一标识 |
| 2 | user_id | TEXT | FK → users.id, INDEX | 所属用户 |
| 3 | title | TEXT(200) | DEFAULT '新对话' | 会话标题 |
| 4 | created_at | DATETIME | | 创建时间 |
| 5 | updated_at | DATETIME | AUTO UPDATE | 最后活跃时间 |

### 5.3 messages — 消息表

| # | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|
| 1 | id | INTEGER | PK, AUTOINCREMENT | 自增主键 |
| 2 | conversation_id | TEXT | FK → conversations.id, INDEX | 所属会话 |
| 3 | role | TEXT(20) | NOT NULL | user / assistant |
| 4 | content | TEXT | NOT NULL | 消息文本 |
| 5 | timestamp | DATETIME | INDEX | 发送时间 |
| 6 | emotion_score | FLOAT | | 情感分值 -1~1 |
| 7 | emotion_label | TEXT(20) | | joy/sadness/anger/fear/neutral |
| 8 | metadata | JSON | | 扩展字段 |

### 5.4 memories — 记忆节点表

| # | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|
| 1 | id | TEXT | PK, UUID | 记忆唯一标识 |
| 2 | user_id | TEXT | NOT NULL, INDEX | 所属用户 |
| 3 | content | TEXT | NOT NULL | 记忆文本（一句话） |
| 4 | emotion_label | TEXT(20) | | 关联情感标签 |
| 5 | importance | FLOAT | DEFAULT 0.5 | 重要度 0~1 |
| 6 | source_message_ids | JSON | | 来源消息 ID 列表 |
| 7 | created_at | DATETIME | | 创建时间 |
| 8 | last_accessed | DATETIME | | 最后检索时间（记忆衰减用） |
| 9 | deprecated | BOOLEAN | DEFAULT FALSE | 是否已废弃 |

### 5.5 memories_fts — 全文搜索虚拟表

| # | 列名 | 类型 | 说明 |
|---|------|------|------|
| 1 | content | TEXT | 从 memories.content 自动同步 |

**同步机制**：
- `memories_ai`：INSERT 后自动写入 FTS 索引
- `memories_ad`：DELETE 后自动从 FTS 索引删除
- `memories_au`：UPDATE 后自动更新 FTS 索引

### 5.6 ChromaDB — 向量存储（非 SQL）

| 属性 | 值 |
|------|------|
| 存储位置 | `backend/data/chroma/` |
| Collection 命名 | `memories_{user_id}`（每用户独立） |
| 向量来源 | TF-IDF (256维) 或 Sentence-Transformers (384维) |
| 存储内容 | 记忆 ID、向量、元数据(content, emotion, importance) |

---

## 6. API 接口一览

### 认证

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/auth/register` | — | 注册，返回用户信息（201）/ 409 |
| POST | `/api/auth/login` | — | 登录，返回 JWT token |
| GET | `/api/auth/me` | Bearer | 获取当前用户信息 |

### 聊天

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/chat` | Bearer | 发送消息，返回 AI 回复。请求体 `{"message":"...","conversation_id":"..."(可选)}` |

### 会话

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/conversations` | Bearer | 创建新会话 |
| GET | `/api/conversations` | Bearer | 获取会话列表（含消息数） |
| GET | `/api/conversations/{id}/messages` | Bearer | 获取会话消息历史（含情感标签） |

### 记忆

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/api/memories` | Bearer | 列出所有记忆 |
| GET | `/api/memories/search?q=xxx&limit=5` | Bearer | 多路检索记忆 |

---

## 7. 对话处理完整流程

以一次用户对话为例，展示 V0.2 完整数据流：

```
用户发送 "我想周末出去玩"
         │
         ▼
    ┌─────────────┐
    │ api/chat.py  │  JWT 认证 → 解析 ChatRequest
    └──────┬──────┘
           │
           ▼
    ┌──────────────────┐
    │ chat_service.py   │
    │  send_message()   │
    └──────┬───────────┘
           │
    ┌──────▼────────────────────────────────────┐
    │ 阶段1: _get_or_create_conversation        │
    │       查/建 conversations 行              │
    ├──────┬────────────────────────────────────┤
    │ 阶段2: _load_recent_messages              │
    │       查 messages 表（最近20条）           │
    ├──────┬────────────────────────────────────┤
    │ 阶段3: _retrieve_memories (V0.2)          │
    │       用户消息 → TF-IDF embedding          │
    │       → ChromaDB 向量检索 (路1)            │
    │       → SQLite FTS5 关键词检索 (路2)       │
    │       → RRF 融合取 Top-3                  │
    │       → 注入 system prompt:               │
    │         "你记得用户之前提到过：             │
    │          - 用户最喜欢在周末去爬山"          │
    ├──────┬────────────────────────────────────┤
    │ 阶段4: _save_message("user", ...)         │
    │       INSERT INTO messages (role=user)    │
    ├──────┬────────────────────────────────────┤
    │ 阶段5: _analyze_and_update_emotion (V0.2) │
    │       LLM 分析用户消息情感                 │
    │       → UPDATE messages SET               │
    │         emotion_score=0.1,                │
    │         emotion_label="neutral"           │
    ├──────┬────────────────────────────────────┤
    │ 阶段6: _llm.chat(messages)                │
    │       DeepSeek API → "周末可以去爬山..."   │
    ├──────┬────────────────────────────────────┤
    │ 阶段7: _save_message("assistant", ...)    │
    │       INSERT INTO messages (role=assistant)│
    ├──────┬────────────────────────────────────┤
    │ 阶段8: _trigger_memory_extraction (V0.2)  │
    │       暂存上下文至 _pending_extraction     │
    ├──────┬────────────────────────────────────┤
    │ 阶段9: _update_conversation_meta          │
    │       UPDATE conversations SET            │
    │       title="我想周末出去玩",              │
    │       updated_at=now()                    │
    └──────┴────────────────────────────────────┘
           │
           ▼
    ┌──────────────┐
    │ api/chat.py   │  返回 ChatResponse
    │               │  同时 pop_extraction_context()
    │               │  → BackgroundTasks.add_task()
    └──────────────┘
           │
           ▼  (后台线程，不阻塞响应)
    ┌──────────────────────────┐
    │ _extract_memories_bg()   │
    │ 独立 db session           │
    │ → MemoryService          │
    │   .extract_memories()    │
    │                          │
    │  1. LLM 分析对话         │
    │  2. 提取记忆 JSON         │
    │  3. semantic dedup       │
    │  4. TF-IDF embedding     │
    │  5. INSERT INTO memories │
    │  6. ChromaDB.add()       │
    └──────────────────────────┘
```

---

## 8. 可扩展性设计

### 8.1 切换大模型

```python
# 新建 my_provider.py
from app.services.base import LLMProvider

class MyProvider(LLMProvider):
    def chat(self, messages, **kwargs):
        # 你的实现
        ...

# 在 api/chat.py 和 api/memory.py 中替换
from app.services.my_provider import MyProvider
_llm = MyProvider()
```

### 8.2 切换向量存储

```python
# 新建 qdrant_store.py
from app.services.vector_store import VectorStore

class QdrantStore(VectorStore):
    # 实现 add / search / delete / count
    ...

# 在 api/chat.py 和 api/memory.py 中替换
from app.services.qdrant_store import QdrantStore
vector_store=QdrantStore()
```

### 8.3 切换 Embedding 模型

```python
# 在 api/chat.py 中将 TFIDFEmbeddingProvider()
# 替换为 SentenceTransformersProvider()
from app.services.embedding_service import SentenceTransformersProvider
embedding_provider=SentenceTransformersProvider()
```

### 8.4 切换数据库

修改 `.env` 中的 `DATABASE_URL`：
```
# SQLite (当前)
DATABASE_URL=sqlite:///./data/treehole.db

# PostgreSQL
DATABASE_URL=postgresql://user:pass@localhost:5432/treehole
```

### 8.5 新增管道阶段

在 `ChatService.send_message()` 中，以 `# === V0.x 扩展点 ===` 标记的位置插入新阶段即可：

```python
# 示例：V0.3 添加知识图谱检索
# === V0.3: retrieve_knowledge_graph ===
knowledge = self._retrieve_kg(db, user_id, message)
llm_messages = self._build_messages(history, message, memory_context, knowledge)
```

---

> 文档结束。项目完整源码位于 `backend/` 目录下。
