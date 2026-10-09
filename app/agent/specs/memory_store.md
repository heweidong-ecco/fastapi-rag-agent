# `app/agent/memory_store.py`

## ✅ 做了什么

**长期记忆**（Mem0 · **本地模式**，数据落 `.mem0/`）：`search_user_memory` / 写入路径。

- 客户端构造用 **`Memory.from_config(dict)`**。
  ⚠️ **⛔ 不是 `Memory(dict)`** —— `mem0ai>=2.0` 的 `__init__` 只接受 `MemoryConfig` 对象。

## 🟡 做到哪 / 缺什么

- **5 处产品代码引用 · 1 个测试文件提到**（`app/tests/test_agent_repairs.py`）。
- 用它的链路：`app/agent/agent_graph_advanced.py` · `agent_graph_advanced_learning.py`
  · `app/routing/api_v1_agent.py` —— 即**二代/三代 Agent 在入口注入长期记忆**。

## ⚠️ 看代码会误判的地方 ⭐

1. 🔴 **mem0 的签名漂移【修过两次】，且第一次没修完**（2026-09-20）：
   - 第一处：`search(query, user_id=…, limit=…)` **不成立** —— mem0 2.x 是
     `search(query, *, top_k=20, filters=None, …)`：**不收 `user_id`**、`limit` **已改名 `top_k`**。
   - 第二处：**返回形状也变了**。
   🔴 **第一处为什么没一次修完**：我当时只验了「**不抛异常 + `len()==1`**」
   ⇒ 这个判据**量不到"返回形状"** ⇒ 第二处才暴露。
   ⇒ 📌 本仓立场：**判据要量到你真正在意的那个量**（同族：`docs/复盘/2026-10-05-拿代理量当判据.md`）。
2. ⚠️ **本地模式的 `user_id` 是【过滤条件】，不是"谁在问"** ——
   ⛔ 别把它当成身份认证的落点（身份在 `app/access/` 那条线上）。
3. ⚠️ **`.mem0/` 在 `.gitignore` 里** ⇒ 记忆**不随仓库走**。换机/重建 = 记忆为空，**不是丢数据**。

## 关联

- `app/tests/test_agent_repairs.py` —— 两处 mem0 漂移的守卫（本文件的两条教训都钉在那）
- `docs/说明/mcp长驻会话-调研-20261008.md`（⛔ 文件名以实际为准）
- 🔴 **本仓另一个项目 `memory-system` 是【独立系统】** —— ⛔ 别把它与这个模块混为一谈
