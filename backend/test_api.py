"""V0.2 API 端到端测试：记忆提取 + 情感分析 + 多路检索。"""
import urllib.request, json, sys, time

BASE = "http://localhost:8000"

def req(method, path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    r = urllib.request.Request(f"{BASE}{path}", data=body, headers=headers, method=method)
    resp = urllib.request.urlopen(r)
    return json.loads(resp.read())

# 1. 注册新用户（避免旧数据干扰）
print("=" * 50)
print("1. 注册新用户...")
try:
    user = req("POST", "/api/auth/register", {"username": "v02test", "password": "test123456"})
    print(f"   ✅ 注册成功: {user['username']}")
except Exception as e:
    print(f"   (可能已存在) {e}")
    login = req("POST", "/api/auth/login", {"username": "v02test", "password": "test123456"})
    token = login["access_token"]
    print("   ✅ 登录成功")

# 2. 登录
print("\n2. 登录...")
login = req("POST", "/api/auth/login", {"username": "v02test", "password": "test123456"})
token = login["access_token"]
print(f"   ✅ token={token[:30]}...")

# 3. 第一轮对话 — 设置一个可记忆的信息
print("\n3. 第一轮对话（分享个人信息）...")
chat1 = req("POST", "/api/chat", {
    "message": "你好树洞！我叫小明，今年28岁，是一个程序员。我最喜欢在周末去爬山。"
}, token=token)
cid = chat1["conversation_id"]
print(f"   用户: 我叫小明，今年28岁...")
print(f"   树洞: {chat1['content'][:80]}...")

# 等待后台记忆提取完成
print("\n4. 等待后台记忆提取（5秒）...")
time.sleep(5)

# 5. 第二轮对话 — 测试记忆是否被召回
print("\n5. 第二轮对话（测试记忆召回）...")
chat2 = req("POST", "/api/chat", {
    "message": "我想周末出去玩，有什么建议吗？",
    "conversation_id": cid,
}, token=token)
print(f"   用户: 我想周末出去玩，有什么建议吗？")
print(f"   树洞: {chat2['content'][:150]}...")

# 6. 检查记忆表
print("\n6. 检查记忆存储...")
memories = req("GET", "/api/memories?limit=10", token=token)
print(f"   ✅ 共 {len(memories)} 条记忆:")
for m in memories:
    print(f"      [{m.get('emotion_label','?')}] {m['content']} (重要度:{m['importance']})")

# 7. 检查消息情感分析
print("\n7. 检查消息情感标签...")
msgs = req("GET", f"/api/conversations/{cid}/messages", token=token)
for m in msgs:
    if m["role"] == "user":
        es = m.get("emotion_score") or 0.0
        el = m.get("emotion_label") or "?"
        print(f"   [{el}] score={es:.2f} → {m['content'][:50]}")

# 8. 测试记忆搜索
print("\n8. 测试记忆搜索...")
from urllib.parse import quote
search = req("GET", f"/api/memories/search?q={quote('爬山')}&limit=3", token=token)
print(f"   搜索 '爬山' → {len(search)} 条结果:")
for item in search:
    print(f"      {item['content']}")

print("\n" + "=" * 50)
print("V0.2 端到端测试完成!")
