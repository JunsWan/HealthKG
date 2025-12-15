### 📄 项目协作文档 (README.md)

请将以下内容保存为项目根目录下的 `README.md`。

````markdown
# Cognitive Intelligence Project: 运动健康助手 (Multi-Agent System)

本项目是一个基于大模型的多智能体运动健康助手。
目前 **多智能体调度 (MAS)**、**用户记忆系统** 与 **前端交互** 已搭建完毕。
**知识图谱 (KG) 检索** 目前使用 Mock 数据，需要接入真实的 Neo4j 数据库。

---

## 📂 核心目录说明

```text
code/
├── app.py                  # [入口] Streamlit 前端与 Session 管理
├── agents/                 # [核心] 智能体编排 (Router, Planner, Reasoner)
│   ├── subflows.py         # ★ 工作流控制：调用 KG 接口的地方
│   └── schemas.py          # 结构化输出定义
├── memory/                 # [记忆] 用户画像与历史记录 (Graph RAG)
├── tools/                  # [接口] 外部工具
│   └── kg_retrieval.py     # ★★★ KG 组开发重点：图谱检索接口实现
└── data/                   # 本地数据 (包含目前的 Mock JSON)
````

## 🚀 开发环境

1.  **依赖安装**:
    ```bash
    pip install streamlit openai networkx neo4j
    ```
2.  **启动应用**:
    ```bash
    streamlit run app.py
    ```

-----

## 🤝 协作接口规范 (For KG Team)

KG 组的主要任务是修改 `tools/kg_retrieval.py`，将目前的关键词匹配替换为 **Neo4j Cypher 查询** 或 **向量检索**。

系统会在 `subflows.py` 中自动调用以下两个函数。**请务必保持函数签名 (Input/Output) 不变。**

### 1\. 运动图谱检索 (`retrieve_exercise_kg`)

  * **功能**: 根据用户的模糊需求或 Agent 提取的关键词，从运动图谱中找出最匹配的动作。
  * **输入 (`args: Dict`)**:
      * `query` (str): 搜索关键词（如 "练胸"、"膝盖痛 康复"）。
      * `topk` (int): 需要返回的数量（默认为 8）。
      * *(扩展)*: 未来如果 Agent 传入了 `muscle` 或 `difficulty`，也可在此解析。
  * **输出 (`List[Dict]`)**: 返回一个字典列表，每个字典代表一个节点/知识点。

**必须包含的字段**:

```python
[
    {
        "evidence_id": "unique_id_from_neo4j",  # 节点的唯一标识
        "name": "杠铃卧推",                       # 动作名称
        "summary": "针对胸大肌中部的基础复合动作...", # 简短描述/简介
        "fields": {                             # 其他属性放在这里
            "target_muscle": "Chest",
            "difficulty": "Medium",
            "equipment": "Barbell"
        },
        "source": "Neo4j_Exercise"              # 数据来源标识
    },
    # ...
]
```

### 2\. 饮食图谱检索 (`retrieve_nutrition_kg`)

  * **功能**: 查询食物热量、营养素或饮食建议。
  * **输入**: 同上。
  * **输出**: 结构同上，但 `fields` 中应包含 `calories`, `protein`, `carb` 等信息。

-----

## 🛠️ Neo4j 接入指南 (建议方案)

建议在 `tools/` 下新建 `neo4j_client.py` 单例模式管理连接，然后在 `kg_retrieval.py` 中调用。

**简单的模糊查询 Cypher 示例**:

```cypher
// 查找名称包含关键词的动作，或者描述包含关键词的动作
MATCH (n:Exercise)
WHERE n.name CONTAINS $keyword OR n.description CONTAINS $keyword
RETURN n
LIMIT $topk
```

````

---

### 💡 给你的 Neo4j 实施建议 (Cheat Sheet)

既然你对 Neo4j 不太熟，这里有一份标准代码（"抄作业"模板）。你可以把这段代码发给负责图谱的队友，或者你自己写进 `tools/kg_retrieval.py` 里。

你需要用到 Python 的官方库：`pip install neo4j`

#### 1. 修改 `tools/kg_retrieval.py` 引入 Neo4j 连接

```python
# tools/kg_retrieval.py (修改版建议)
import os
from neo4j import GraphDatabase
from typing import List, Dict, Any

# --- 配置部分 (建议移到 config.py 或环境变量) ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your_password"

# 建立驱动 (最好做成单例，这里为了演示直接写)
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def _run_cypher(query: str, params: dict = None):
    """执行 Cypher 语句的通用函数"""
    with driver.session() as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]

def retrieve_exercise_kg(args: Dict[str, Any], exercise_kg: Dict[str, Any]=None) -> List[Dict[str, Any]]:
    """
    实际连接 Neo4j 的版本
    注意：exercise_kg 参数可能不再需要，或者作为 fallback
    """
    user_query = args.get("query", "")
    topk = args.get("topk", 5)

    if not user_query:
        return []

    # 编写 Cypher: 这里用简单的 CONTAINS 做模糊匹配
    # 也可以用全文索引 (Fulltext Index) 效果更好
    cypher_sql = """
    MATCH (n:Exercise) 
    WHERE toLower(n.name) CONTAINS toLower($q) 
       OR toLower(n.description) CONTAINS toLower($q)
       OR toLower(n.target_muscle) CONTAINS toLower($q)
    RETURN n.id AS id, n.name AS name, n.description AS summary, n 
    LIMIT $k
    """
    
    try:
        raw_results = _run_cypher(cypher_sql, {"q": user_query, "k": topk})
        
        # 格式化为 Agent 需要的标准格式
        evidence_list = []
        for row in raw_results:
            node_props = row.get("n", {})
            evidence_list.append({
                "evidence_id": str(row.get("id", node_props.get("id", "unknown"))),
                "name": row.get("name", "Unknown Exercise"),
                "summary": row.get("summary", "")[:100] + "...", # 截断一下防止Token爆炸
                "fields": {
                    "muscle": node_props.get("target_muscle"),
                    "equipment": node_props.get("equipment"),
                    "difficulty": node_props.get("difficulty")
                },
                "source": "Neo4j_Prod"
            })
        return evidence_list

    except Exception as e:
        print(f"[KG Error] Neo4j query failed: {e}")
        # 如果数据库挂了，回退到原来的 keyword search (mock)
        from core.json_utils import dumps # 复用你原来的逻辑
        if exercise_kg:
            return _original_simple_keyword_retrieve(exercise_kg, user_query, topk)
        return []

# Nutrition 同理...
````
