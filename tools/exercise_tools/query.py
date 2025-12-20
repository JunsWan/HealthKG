from neo4j import GraphDatabase
import neo4j

class ExerciseKGQuery:

    def __init__(self, uri, auth):
        self.driver = GraphDatabase.driver(uri, auth=auth)

    def close(self):
        self.driver.close()

    def fetch_candidates(
        self,
        target_body_part,
        injury_body_part,      # 🔁 改成复数，list
        available_equipment,
    ):
        query = """
            MATCH (ev:ExerciseVariant)
            MATCH (ev)-[:TRAINS_BODY_PART]->(:TrainingBodyPart {name: $target_body_part})

            /* 排除 instruction 中涉及任一受伤部位 */
            WHERE NOT EXISTS {
                MATCH (ev)-[:INVOLVES_BODY_PART]->(ibp:InstructionBodyPart)
                WHERE ibp.name IN $injury_body_part
            }

            /* equipment */
            OPTIONAL MATCH (ev)-[:USES_EQUIPMENT]->(eq:Equipment)

            /* muscles */
            OPTIONAL MATCH (ev)-[:TARGETS]->(tm:Muscle)
            OPTIONAL MATCH (ev)-[:SYNERGIZES]->(sm:Muscle)
            OPTIONAL MATCH (ev)-[:STABILIZES]->(stm:Muscle)

            RETURN
                ev.id           AS id,
                ev.name         AS name,
                ev.instructions AS instructions,
                ev.utility      AS utility,
                ev.force        AS force,

                /* equipment list */
                collect(DISTINCT eq.name) AS equipment,

                /* muscle groups */
                collect(DISTINCT tm.name)  AS target_muscles,
                collect(DISTINCT sm.name)  AS synergist_muscles,
                collect(DISTINCT stm.name) AS stabilizer_muscles
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                target_body_part=target_body_part,
                injury_body_part=injury_body_part,  # 🔁 注意参数名
                available_equipment=available_equipment,
            )
            return [record.data() for record in result]


    def fetch_all_training_body_parts(self):
        query = """
        MATCH (bp:TrainingBodyPart)
        RETURN DISTINCT bp.name AS name
        ORDER BY name
        """
        with self.driver.session() as session:
            return [r["name"] for r in session.run(query)]


    def fetch_all_equipment(self):
        query = """
        MATCH (eq:Equipment)
        RETURN DISTINCT eq.name AS name
        ORDER BY name
        """
        with self.driver.session() as session:
            return [r["name"] for r in session.run(query)]

    def search_exercises(self, keyword: str, excludes: list = None, limit: int = 5):
        """
        [升级版搜索] 支持关键词模糊匹配 + 排除词过滤
        """
        # 1. 处理默认参数
        if excludes is None:
            excludes = []
            
        # 2. 动态构建排除语句 (Cypher Logic)
        # 如果 excludes = ["Squat", "Jump"]
        # 生成: AND NOT (toLower(ev.name) CONTAINS "squat") AND NOT (toLower(ev.name) CONTAINS "jump")
        exclude_clause = ""
        if excludes:
            conditions = []
            for ex in excludes:
                # 注意转义和转小写
                safe_ex = ex.replace("'", "").replace('"', '').lower()
                conditions.append(f"NOT toLower(ev.name) CONTAINS '{safe_ex}'")
            
            # 拼接到 SQL 中
            exclude_clause = "AND (" + " AND ".join(conditions) + ")"

        # 3. 编写完整 Cypher
        query = f"""
        MATCH (ev:ExerciseVariant)
        WHERE (
            /* 匹配名字 */
            toLower(ev.name) CONTAINS toLower($kw)
            OR EXISTS {{
                /* 匹配部位 (注意新版语法可能是 :TRAINS_BODY_PART|TARGETS) */
                MATCH (ev)-[:TRAINS_BODY_PART|TARGETS]->(n)
                WHERE toLower(n.name) CONTAINS toLower($kw)
            }}
        )
        {exclude_clause}  /* <--- 插入排除逻辑 */
        
        RETURN DISTINCT
          ev.id           AS id,
          ev.name         AS name,
          ev.instructions AS instructions,
          ev.utility      AS utility,
          ev.mechanics    AS mechanics
        LIMIT $limit
        """
        
        with self.driver.session() as session:
            result = session.run(query, kw=keyword, limit=limit)
            return [record.data() for record in result]


class ExerciseKGExampleQuery:

    def __init__(self, uri, auth):
        self.driver = GraphDatabase.driver(uri, auth=auth)

    def close(self):
        self.driver.close()

    def fetch_example_exercises(self, limit=20):
        query = """
        MATCH (ev:ExerciseVariant)-[:TRAINS_BODY_PART]->(bp:TrainingBodyPart)
        RETURN
          ev.id AS id,
          ev.name AS name,
          bp.name AS body_part,
          ev.instructions AS instructions,
          ev.mechanics AS mechanics,
          ev.force AS force
        LIMIT $limit
        """

        with self.driver.session() as session:
            result = session.run(query, limit=limit)
            return [record.data() for record in result]
