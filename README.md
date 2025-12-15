# Cognitive Intelligence Project: 运动健康助手 (Multi-Agent System)

本项目构建了一个基于大模型的多智能体运动健康助手。目前负责 **多智能体调度 (MAS)** 与 **用户记忆 (User Memory)** 的核心逻辑。

**注意**：知识图谱 (KG) 的检索部分目前为 Mock/空接口，需由负责 KG 的同学在 `tools/kg_retrieval.py` 中实现。

---

## 📂 项目结构说明

```text
code/
├── app.py                  # [Entry] Streamlit 前端入口，负责 Session 管理和 UI 渲染
├── agents/                 # [Core] 智能体与编排逻辑
│   ├── router.py           # 意图路由 (Router)
│   ├── subflows.py         # 子工作流编排 (控制数据流向的核心)
│   ├── runner.py           # LLM 调用与 Trace 记录封装
│   ├── schemas.py          # Structured Outputs 定义 (JSON Schema)
│   ├── prompts.py          # 各 Agent 的 System Prompt
│   └── response_generator.py # 最终回复生成模块
├── core/
│   ├── llm.py              # OpenAI API 客户端封装
│   └── config.py           # 配置读取
├── memory/                 # [Memory] 用户记忆模块
│   ├── graph_store.py      # 用户记忆图谱的操作逻辑 (增删改查)
│   └── persistence.py      # JSON 文件读写
├── tools/                  # [Interface] 外部工具接口
│   └── kg_retrieval.py     # ★ KG 组员开发点：图谱检索接口
├── data/                   # 数据存储
│   ├── user_memory_graph.json # 用户记忆图谱 (持久化)
│   ├── exercise_kg.json    # 运动知识图谱 (源数据)
│   └── nutrition_kg.json   # 饮食知识图谱 (源数据)
└── pages/                  # Streamlit 调试页面
    ├── 1_Trace.py          # 查看 Agent 思考链 (Debug 用)
    └── ...
````

## 🚀 目前已实现功能

1.  **多智能体编排 (Orchestration)**:
      * 实现了 `Router` -\> `Subflow` -\> `Specialized Agents` 的分层架构。
      * 支持意图：咨询问答 (FAQ)、方案规划 (Plan)、记忆查询 (Query)、日志上报 (Log)。
2.  **长期记忆系统 (Long-term Memory)**:
      * 基于 Graph (JSON) 的用户画像、偏好、历史记录存储。
      * `MemoryRetriever`: 自动提取与当前对话相关的记忆。
      * `MemoryUpdater`: 基于对话内容自动更新用户图谱 (Patch Ops)。
3.  **结构化输出 (Structured Outputs)**:
      * 所有 Agent 均强制使用 JSON Schema 输出，保证系统稳定性。
4.  **调试工具**:
      * 前端提供 `Trace` 页面，可实时查看每个 Agent 的耗时、输入与 JSON 输出。

-----

## 🤝 协作接口说明 (For KG Team)

KG 组员的主要工作集中在 **`tools/kg_retrieval.py`**。
目前系统会在 `subflows.py` 中调用以下两个函数。请保持函数签名一致，修改内部实现以对接 Neo4j 或向量库。

### 1\. 运动图谱检索 (`retrieve_exercise_kg`)

  * **调用时机**: 当用户咨询动作，或 Agent 需要规划训练计划时。
  * **输入 (`args`)**:
      * `query` (str): 用户的原始问题，或 Agent 生成的搜索关键词。
      * `topk` (int): 需要返回的数量。
      * *(可选)* `muscle`, `difficulty` 等过滤参数（视 Agent 生成的 args 而定）。
  * **输出**: `List[Dict]`，每个 Dict 代表一条证据/知识点。

<!-- end list -->

```python
# tools/kg_retrieval.py

def retrieve_exercise_kg(args: dict, kg_graph: dict) -> list:
    """
    TODO: Replace with actual Neo4j/Vector DB query.
    Current: Returns mock data or simple keyword match from json.
    """
    query = args.get("query", "")
    # ... 实现你的检索逻辑 ...
    return [
        {
            "evidence_id": "ex_001",
            "name": "杠铃卧推",
            "summary": "锻炼胸大肌的黄金动作...",
            "fields": {"target": "Chest", "equipment": "Barbell"},
            "source": "ExerciseKG"
        },
        # ...
    ]
```

### 2\. 饮食图谱检索 (`retrieve_nutrition_kg`)

  * **调用时机**: 当用户咨询食物热量、营养搭配，或生成饮食计划时。
  * **输入/输出**: 结构同上。

-----

## 🛠️ 快速启动

1.  **配置环境**:
    ```bash
    pip install streamlit openai networkx
    ```
2.  **运行系统**:
    ```bash
    streamlit run app.py
    ```
3.  **配置 LLM**:
      * 启动后在侧边栏/Settings页填写 API Key 和 Base URL。
4.  **调试**:
      * 在主页对话。
      * 点击左侧 `Trace` 页面查看 Agent 内部交互细节。

-----

## ⚠️ 注意事项

  * **Schema 变更**: 如果修改了 Agent 的输出字段，请务必同步修改 `agents/schemas.py`。
  * **状态管理**: `st.session_state.user_memory_graph` 是内存中的热数据，对话结束会自动保存到 `data/` 目录。手动修改 JSON 文件需重启服务。

<!-- end list -->

```
