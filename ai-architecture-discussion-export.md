# AI 架构讨论导出

时间：2026-07-19
项目：D:\code\myhouse

## 1. 当前整体架构

这套 AI 链路大致是：

```text
LangGraph 编排流程
+ DeepSeek 做理解、生成和工具决策
+ BGE-small 做向量化
+ ChromaDB 做 Skill 文档向量检索
+ 白名单工具执行业务
+ MySQL / Redis 做状态持久化
```

它不是把全部事情都丢给模型，而是通过确定性业务规则、受控工具、待确认写库机制来约束模型行为。

## 2. LangGraph 的角色

LangGraph 主要负责流程编排，不是单独的 RAG 数据库，也不是完整记忆数据库。

它在项目里负责：

- 根据输入路由到不同业务分支。
- 管理 `call_model -> run_tools -> call_model` 的工具调用循环。
- 通过 `thread_id` 隔离不同聊天线程。
- 通过 checkpoint 保存图执行快照。

当前图不是纯 DAG，因为存在工具循环。

## 3. call_model 是否就是调用 DeepSeek

`call_model` 节点本身只是 LangGraph 里的一个节点名。

实际调用链路是：

```text
_graph_call_model_node
-> ai_svc.call_with_tools(...)
-> ai_service.py
-> 默认 deepseek-v4-flash
-> DeepSeek API
```

如果用户配置切到 OpenAI、智谱、千问或自定义 base_url，也会跟着切过去。

## 4. ReAct 能力

当前系统具备“工具调用版 ReAct”能力：

```text
模型判断下一步
-> 返回 tool_calls
-> 系统执行工具
-> 工具结果回灌给模型
-> 模型继续判断或生成最终回复
```

它不是显式输出 `Thought / Action / Observation` 的经典 ReAct 论文格式，而是基于 function calling 的实用 Agent loop。

## 5. RAG 检索是谁做的

负责 RAG 检索的是：

```text
py/app/services/skill_vector_store.py
```

核心函数：

```python
search_skills(prompt, top_k=5)
```

它做的是 Skill 文档检索：

```text
Skill.md
-> 切块
-> BAAI/bge-small-zh-v1.5 向量化
-> ChromaDB 存储
-> 用户问题向量化
-> ChromaDB 相似度查询
-> 命中的 Skill 片段写入 system prompt
```

如果 BGE 或 ChromaDB 不可用，会退回关键词检索。

## 6. BGE-small 的作用

`BAAI/bge-small-zh-v1.5` 负责 embedding，也就是把文本转成向量。

它不生成回答，只负责向量化：

- 把 `Skill.md` 文档转成向量。
- 把用户 query 转成向量。
- 让 ChromaDB 能做相似度检索。

## 7. ChromaDB 的作用

ChromaDB 是向量数据库。

它负责：

- 保存 Skill 文档向量。
- 根据用户 query 的向量找相似 Skill 片段。
- 返回 top-k 命中结果。

## 8. 当前是否做了工具检索

目前没有单独做“最优工具检索”。

当前方式是：

```text
检索 Skill 文档
-> 把 Skill 片段放进 prompt
-> 把全量工具 schema 给模型
-> 模型自己决定调用哪个工具
```

也就是说：

- 有知识检索。
- 没有工具检索。
- `tool_plan.allowed_tools` 更像 prompt 里的软约束，不是真正过滤工具列表。

后续可升级为：

```text
intent
-> tool_retriever
-> top-k 工具 schema
-> 模型决策
```

## 9. 记忆当前存在哪里

当前是两层：

### 业务记忆

业务会话记忆已经进 MySQL。

表：

```text
ai_thread_state
```

保存内容：

```text
session_context
last_intent
workflow_state
tool_plan
```

### LangGraph checkpoint

LangGraph checkpoint ????? MySQL???? MySQL/Redis ??????

```text
MySQL ai_thread_state / ai_trace + Redis ??
```

里面有 `checkpoints` 表，保存图执行快照。

## 10. 为什么核心记忆不建议只放 Redis

Redis 更适合缓存，不适合作为核心记忆的唯一事实源。

建议分工：

```text
MySQL:
- ai_thread_state
- chat_history
- pending_actions
- workflow_state
- 长期偏好记忆
- 可审计的用户偏好

Redis:
- 临时缓存
- 状态流事件
- 并发锁
- 防重复提交 token
- 工具查询缓存
```

## 11. 记忆切换和隔离

当前记忆隔离主要靠 `thread_id`。

流程：

```text
前端传 chat_thread_id
-> Orchestrator 解析 thread_id
-> 从 ai_thread_state 加载该线程状态
-> 合并 incoming session_context
-> 执行业务流程
-> 保存新的 session_context
```

业务上下文主要包括：

```text
active_workflow
last_completed_workflow
workflow_state
contract_draft
suspended_contract
building_id / building_name
room_id / room_number
tenant_id / tenant_name
```

业务流程切换示例：

```text
正在新建合同
-> 用户说先录电表
-> 合同草稿进入 suspended_contract
-> active_workflow 切到 meter_reading
-> 后续回到合同流程时恢复合同草稿
```

当前业务隔离已经基本够用，前提是不同聊天窗口使用不同 `chat_thread_id`。

## 12. 长期偏好记忆是什么

长期偏好记忆是跨会话保存的用户习惯。

例如：

```json
{
  "preferred_building_id": 3,
  "preferred_building_name": "石潭布",
  "money_format": "two_decimals",
  "default_view": "contract_first"
}
```

它和 `session_context` 不一样：

- `session_context` 是当前聊天线程的业务状态。
- 长期偏好记忆是跨线程、跨会话复用的用户偏好档案。

当前项目还没有通用的“记住这个”功能，只有业务线程上下文记忆。

## 13. 评测集是什么

评测集是一批固定测试题，用来检查 AI 系统改动后有没有退化。

例子：

```text
输入：
帮我新建石潭布3栋502的合同，租客张三，月租1800

期望：
- 识别为 contract_create
- 抽取 room_number=502
- 生成待确认操作
- 不能直接写库
```

评测集不会让 AI 自动变聪明，但能帮助开发者持续调优 prompt、工具、RAG 和记忆系统。

## 14. 建议升级方向

优先级建议：

```text
工具裁剪
-> 调试面板
-> 记忆分层
-> 评测集
-> checkpoint 统一存储
```

更具体地说：

- 增加工具检索 / 工具裁剪，减少误调工具。
- 做 AI trace 调试面板，显示当前 workflow、命中的 Skill、调用工具、pending action。
- 把记忆分层成短期上下文、业务流程状态、长期偏好、待确认操作。
- 建一批真实业务评测样本。
LangGraph checkpoint ????? MySQL???? MySQL/Redis ??????

## 15. 总体判断

这套架构方向是合理的。

它的聪明点在于：

- 没有迷信大模型。
- 用 LangGraph 控制流程。
- 用白名单工具约束执行。
- 用待确认机制保护写库。
- 用 BGE + Chroma 做轻量业务知识 RAG。
- 用 MySQL 保存业务上下文状态。

后续升级重点不是换框架，而是增强：

- 工具选择边界
- 记忆分层
- 可观测性
- 回归评测
