# Cognitive Health Agent: 基于多智能体协作的个人健康管理系统

> **A Multi-Agent System for Personalized Fitness & Diet Management backed by Knowledge Graphs**

本项目构建了一个垂直领域的**认知型运动健康助手**。不同于通用的对话机器人，本系统采用 **Router-Agent** 架构，将复杂的健康管理任务解耦为饮食记录、运动追踪、计划生成与专业咨询四个专项工作流。通过结合 **LLM 的语义理解能力**与 **Neo4j 知识图谱的逻辑存储能力**，实现了具备长期记忆、精准推理和主动关怀的智能服务。

---

## 🔄 核心工作流 (Core Workflows)

本系统将用户意图精准分发至专精的智能体，支持以下四种核心交互模式：

### 1. 智能饮食追踪 (Intelligent Diet Logging)

* **场景**：用户输入非结构化的自然语言（如：“中午吃了100g番茄炒蛋和一碗米饭”）。
* **处理流**：`Router` -> `IntentParser` (实体提取) -> `DietKG` (营养素查询) -> `DietLogger` (热量计算) -> `MemoryUpdater`。
* **能力**：自动将模糊的菜名映射为图谱中的标准实体，计算热量与三大营养素（P/C/F），并写入用户记忆图谱。

### 2. 运动负荷管理 (Workout Tracking)

* **场景**：用户记录训练内容（如：“今天深蹲 80kg 做组，感觉膝盖有点不舒服”）。
* **处理流**：`Router` -> `WorkoutLogger` (动作匹配) -> `MemoryUpdater` (状态更新)。
* **能力**：识别训练动作、容量（Volume）及身体反馈。若检测到“不舒服”，会自动在图谱中创建或更新 `Injury` 节点，用于后续的风控预警。

### 3. 个性化方案生成 (Adaptive Planning)

* **场景**：用户请求生成计划（如：“帮我制定一个下周的减脂饮食计划”）。
* **处理流**：`Router` -> `PlanGenerator` (RAG + 逻辑推理) -> `OutputFormatter`。
* **能力**：`PlanGenerator` 不会凭空捏造，而是先检索用户的 **Profile**（体重、目标）、**Preferences**（忌口、器械）和 **History**（最近练了什么），基于这些约束生成结构化的 JSON 计划。

### 4. 专业知识问答 (Domain Q&A)

* **场景**：用户咨询专业问题（如：“减脂期晚上能吃碳水吗？”）。
* **处理流**：`Router` -> `FAQAgent` -> `RAG Retrieval` -> `ResponseGenerator`。
* **能力**：基于挂载的专业知识库回答问题，拒绝通用模型的幻觉，确保建议的科学性。

---

## 🧩 系统设计特性 (System Characteristics)

### 1. 多智能体编排 (Multi-Agent Orchestration)

采用 **Router-Subflow** 模式。

* **Router** 仅负责意图分类，不处理具体业务，降低了 Token 消耗并提高了准确率。
* 下游挂载 `DietLogger`, `WorkoutLogger`, `PlanGenerator` 等多个专家 Agent，各司其职，互不干扰。

### 2. 状态化记忆 (Stateful Long-Term Memory)

摒弃了传统的“纯文本向量库”记忆模式，采用 **Neo4j 图数据库**存储结构化记忆。

* **结构化**：用户的每一次交互都被转化为 `Event` 节点，与 `User`、`Recipe`、`Exercise` 节点建立边关系。
* **时序性**：系统具备完整的时间感知能力，能进行“上次训练是几天前”、“膝盖疼持续了多久”等复杂的时间序列推理。

### 3. 双知识图谱架构 (Dual-KG Architecture)

系统底层同时挂载了两个异构的领域图谱，通过配置中心实现分流：

* **Exercise KG**: 存储解剖学数据、动作库、器械映射关系。
* **Diet KG**: 存储食谱、食材、微量元素及热量数据。
这种分离设计保证了领域知识的专业度，避免了单一图谱的 schema 过于复杂。

---

## 🚀 技术亮点与挑战 (Technical Highlights)

在实现过程中，我们针对 LLM 在垂直落地中的常见问题（幻觉、上下文丢失、Schema 适配）进行了针对性优化：

### 1. 深度上下文缝合 (Context Stitching)

* **问题**：在多轮对话中（如 A: "吃了牛肉" -> B: "多少?" -> A: "100g"），传统的单轮 RAG 无法处理孤立的参数输入。
* **方案**：实现了基于对话历史的回溯机制。当识别到补充性输入时，自动提取上一轮的实体上下文，合成完整语义送入 Agent，实现流畅的追问与补全。

### 2. 跨语言语义对齐 (Cross-Lingual RAG)

* **问题**：用户使用中文输入，而高质量的开源营养图谱（RecipeKG）主要为英文实体。
* **方案**：在检索链路中植入了 **Entities Translator**。通过 LLM 将提取的中文实体精准映射为英文专业术语（如 "番茄炒蛋" -> "Tomato Scrambled Eggs"），再进行图谱检索，最后将结果回译，实现了无感的跨语言知识调用。

### 3. 自愈式图谱查询 (Self-Healing Query)

* **问题**：图数据库 Schema 变更或异构数据源导致查询字段不匹配（如 `name` vs `recipe_name`），易引发系统崩溃。
* **方案**：在查询工具层实现了 **Schema Probe（探针）** 机制。当标准查询失败时，系统自动探测数据库当前的元数据结构，动态调整 Cypher 查询语句，显著提升了系统的鲁棒性。

---

## 🛠️ 系统架构 (Architecture)

### 技术栈

* **核心逻辑**: Python, Streamlit
* **大模型**: OpenAI GPT-4o (Function Calling / JSON Mode)
* **知识库**: Neo4j (Graph Database)
* **编排框架**: Custom Multi-Agent Framework (Router -> Subflows -> Agents)

### 模块说明

```text
root/
├── app.py                  # 应用程序入口 (包含会话管理与智能开场白逻辑)
├── core/                   # 核心基础设施
│   ├── config.py           # 双图谱及LLM配置中心
│   ├── llm.py              # LLM 接口封装
│   └── json_utils.py       # 数据解析工具
├── agents/                 # 智能体层 (Agent Layer)
│   ├── router.py           # 意图分发 (Intent Routing)
│   ├── subflows.py         # 业务流编排 (上下文缝合、翻译、查询核心逻辑)
│   ├── message_builder.py  # 提示词构建
│   ├── response_generator.py
│   └── prompts.py          # Agent 人设与 System Prompts
├── memory/                 # 记忆层 (Memory Layer)
│   ├── graph_store.py      # Neo4j 底层读写操作 (Nodes/Edges/Events)
│   └── persistence.py      # 记忆状态管理
├── tools/                  # 工具层 (Tool Layer)
│   ├── diet_tools/         # 饮食相关工具 (含自愈式查询)
│   ├── exercise_tools/     # 运动相关工具
│   └── kg_retrieval.py     # 通用检索接口
├── pages/                  # 前端页面
│   ├── 1_智能体轨迹.py      # 调试工具：可视化 Agent 的思考链 (Trace)
│   ├── 2_用户记忆图谱.py    # 用户画像管理：查看/编辑长期记忆与 JSON 元数据
│   └── 3_设置.py            # API Key 与模型配置
└── data/                   # 图谱数据

```

---

## 🚀 快速开始 (Quick Start)

### 1. 环境准备

确保已安装 Python 3.8+ 及 Neo4j 数据库（可选云服务或本地 Docker）。

```bash
# 安装依赖
pip install streamlit neo4j openai pandas

```

### 2. 配置密钥

在 `core/config.py` 中配置，或通过环境变量注入：

* `OPENAI_API_KEY`: LLM 服务密钥
* `NEO4J_URI` / `PASSWORD`: 运动图谱连接信息
* `DIET_NEO4J_URI` / `PASSWORD`: 饮食图谱连接信息

### 3. 启动应用

```bash
streamlit run app.py

```

### 4. 使用流程

1. **初始化**：首次进入可在 `3_设置.py` 确认模型配置。
2. **交互**：在主页对话框输入自然语言（如“我刚跑了5公里”、“帮我制定一个胸肌训练计划”）。
3. **查看记忆**：在 `2_用户记忆图谱.py` 中实时查看系统如何将非结构化对话转化为结构化图谱节点。
4. **调试**：使用 `1_智能体轨迹.py` 查看多智能体的分发与执行日志。

---

## 🔮 未来展望 (Future Work)

* **多模态输入**：集成视觉模型，支持食物拍照识别并自动查询 KG 计算热量。
* **主动健康干预**：基于时间序列分析，当检测到连续饮食偏差或训练停滞时，主动发起干预对话。
* **可穿戴设备同步**：接入 Apple Health / Garmin API，实现自动化的数据闭环。

---

**Project Members**: 
**Date**: 2025-12