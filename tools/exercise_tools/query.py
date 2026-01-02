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

    def search_exercises(
        self,
        target_part: str,
        exercise_text: str = None,
        excludes: list = None,
        limit: int = 5
    ):
        """
        语义正确版搜索：
        1️⃣ 先按 body_part 精确过滤（TRAINS_BODY_PART）
        2️⃣ 再按 exercise_text 对 name 做模糊匹配
        3️⃣ 返回 body_part(str) + target_muscles(list)
        """

        if excludes is None:
            excludes = []

        # ---------- 排除词 ----------
        exclude_clause = ""
        if excludes:
            conditions = []
            for ex in excludes:
                safe_ex = ex.replace("'", "").replace('"', '').lower()
                conditions.append(f"NOT toLower(ev.name) CONTAINS '{safe_ex}'")
            exclude_clause = "AND " + " AND ".join(conditions)

        # ---------- 是否有 exercise_text ----------
        name_filter = ""
        if exercise_text:
            safe_kw = exercise_text.replace("'", "").replace('"', '')
            name_filter = "AND toLower(ev.name) CONTAINS toLower($exercise_text)"

        # ---------- Cypher ----------
        query = f"""
        MATCH (ev:ExerciseVariant)-[:TRAINS_BODY_PART]->(tbp:TrainingBodyPart)
        WHERE toLower(tbp.name) = toLower($target_part)
        {name_filter}
        {exclude_clause}

        OPTIONAL MATCH (ev)-[:TARGETS]->(tm:Muscle)

        RETURN
            ev.id AS id,
            ev.name AS name,
            ev.instructions AS instructions,
            ev.utility AS utility,
            ev.mechanics AS mechanics,
            head(collect(DISTINCT tbp.name)) AS body_part,
            collect(DISTINCT tm.name) AS target_muscles
        LIMIT $limit
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                target_part=target_part,
                exercise_text=exercise_text,
                limit=limit
            )
            return [r.data() for r in result]



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
