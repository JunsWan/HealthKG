# /tools/diet_tools/query.py

from neo4j import GraphDatabase
from typing import Dict, Any, Optional

class DietKGQuery:

    def __init__(self, uri, auth):
        masked_uri = uri
        print(f"[DietKGQuery] Connecting to: {masked_uri} ...")
        self.driver = GraphDatabase.driver(uri, auth=auth)

    def close(self):
        self.driver.close()

    def fetch_candidates(
        self,
        meal_type: str,
        dish_types: list,
        diet_labels: list,
        health_labels: list,
        forbidden_cautions: list
    ):
        """
        KG 只做硬约束过滤
        """

        query = """
        MATCH (r:Recipe)

        WHERE $meal_type IN r.meal_type
          AND ANY(dt IN r.dish_type WHERE dt IN $dish_types)

          /* diet labels（若有） */
          AND (
            size($diet_labels) = 0
            OR ALL(dl IN $diet_labels WHERE dl IN r.diet_labels)
          )

          /* health preference 加分但不硬过滤 */
          AND NONE(c IN r.cautions WHERE c IN $forbidden_cautions)

        RETURN
          r.id                AS id,
          r.name              AS recipe_name,
          r.calories          AS calories,
          r.servings          AS servings,
          r.cuisine_type      AS cuisine_type,
          r.meal_type         AS meal_type,
          r.dish_type         AS dish_type,
          r.diet_labels       AS diet_labels,
          r.health_labels     AS health_labels,
          r.ingredients       AS ingredients,
          r.total_nutrients   AS total_nutrients
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                meal_type=meal_type,
                dish_types=dish_types,
                diet_labels=diet_labels,
                health_labels=health_labels,
                forbidden_cautions=forbidden_cautions
            )
            return [r.data() for r in result]
        
    def fetch_candidates_with_detail(
        self,
        meal_type: str,
        dish_types: list,
        diet_labels: list,
        health_labels: list,
        forbidden_cautions: list,
        limit: int = 50
    ):
        """
        一次性获取：
        - Recipe 候选
        - Ingredients（含分量）
        - Nutrients（含数值）
        """

        query = """
        MATCH (r:Recipe)

        // 由于列表被存储为字符串，需要特殊处理
        WHERE
          // 处理 meal_type：检查字符串是否包含特定餐次
          ($meal_type IN split(replace(replace(r.meal_type, '[', ''), ']', ''), ', ') 
           OR r.meal_type CONTAINS $meal_type)

          // 处理 dish_type：检查是否包含任一 dish_type
          OR ANY(dt IN $dish_types 
                  WHERE dt IN split(replace(replace(r.dish_type, '[', ''), ']', ''), ', ')
                  OR r.dish_type CONTAINS dt)

          // 处理 diet_labels：如果提供了筛选条件
          AND (
            size($diet_labels) = 0
            OR ALL(dl IN $diet_labels 
                   WHERE dl IN split(replace(replace(r.diet_labels, '[', ''), ']', ''), ', ')
                   OR r.diet_labels CONTAINS dl)
          )

          // 处理 forbidden_cautions：检查是否有禁忌
          AND (
            size($forbidden_cautions) = 0
            OR NONE(fc IN $forbidden_cautions 
                   WHERE fc IN split(replace(replace(r.cautions, '[', ''), ']', ''), ', ')
                   OR r.cautions CONTAINS fc)
          )

        OPTIONAL MATCH (r)-[hi:HAS_INGREDIENT]->(ing:Ingredient)
        OPTIONAL MATCH (r)-[hn:HAS_NUTRIENT]->(nut:Nutrient)

        RETURN
          r.label         AS recipe_id,
          r.name          AS recipe_name,
          r.servings      AS servings,
          r.calories      AS calories,
          r.cuisine_type  AS cuisine_type,
          r.meal_type     AS meal_type,
          r.dish_type     AS dish_type,
          r.diet_labels   AS diet_labels,
          r.health_labels AS health_labels,

          collect(
            DISTINCT {
              name: ing.name,
              quantity: hi.quantity,
              measure: hi.measure,
              weight: hi.weight,
              text: hi.text
            }
          ) AS ingredients,

          collect(
            DISTINCT {
              key: nut.name,
              label: nut.label,
              quantity: hn.quantity,
              unit: hn.unit
            }
          ) AS nutrients
        LIMIT $limit
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                meal_type=meal_type,
                dish_types=dish_types,
                diet_labels=diet_labels,
                forbidden_cautions=forbidden_cautions,
                limit=limit
            )

            return [record.data() for record in result]

    def _probe_db_structure(self):
        """
        当搜索失败时，自动诊断数据库结构
        """
        print("\n[DietKG Diagnostic] === 开始自检 ===")
        with self.driver.session() as session:
            try:
                # 1. 检查有没有 Recipe 节点
                cnt = session.run("MATCH (n:Recipe) RETURN count(n) as c").single()["c"]
                print(f"[DietKG Diagnostic] Recipe 节点数量: {cnt}")
                
                if cnt > 0:
                    # 2. 如果有，采样一个看看属性名叫啥
                    sample = session.run("MATCH (n:Recipe) RETURN n LIMIT 1").single()["n"]
                    print(f"[DietKG Diagnostic] Recipe 属性键采样: {list(sample.keys())}")
                    print(f"[DietKG Diagnostic] Recipe 样本数据: {dict(sample)}")
                else:
                    # 3. 如果没有 Recipe，看看有啥 Label
                    labels = session.run("CALL db.labels()").value()
                    print(f"[DietKG Diagnostic] 数据库中存在的所有 Labels: {labels}")
                    if not labels:
                        print("[DietKG Diagnostic] 🚨 警告：数据库是空的！")
            except Exception as e:
                print(f"[DietKG Diagnostic] 自检失败: {e}")
        print("[DietKG Diagnostic] === 自检结束 ===\n")

    def search_items(self, keyword: str, limit: int = 5):
        """
        [Fixed] 最终修正：根据诊断结果，Recipe 节点使用 name 属性
        """
        results = []
        
        # 1. 搜食谱 (Recipe)
        # 诊断确认：属性名为 name，且 calories 存在
        cypher_recipe = """
        MATCH (r:Recipe)
        WHERE toLower(r.name) CONTAINS toLower($kw)
        RETURN 
            elementId(r) as id, 
            r.name as name, 
            COALESCE(r.calories, 0) as cal, 
            'Recipe' as type, 
            COALESCE(r.dish_type, '') as desc
        LIMIT $limit
        """
        
        # 2. 搜食材 (Ingredient)
        cypher_ing = """
        MATCH (i:Ingredient)
        WHERE toLower(i.name) CONTAINS toLower($kw)
        RETURN 
            elementId(i) as id, 
            i.name as name, 
            'Ingredient' as type, 
            'Basic Ingredient' as desc
        LIMIT $limit
        """
        
        with self.driver.session() as session:
            try:
                # 1. 搜食谱
                ret_r = session.run(cypher_recipe, kw=keyword, limit=limit)
                for record in ret_r:
                    data = record.data()
                    # list转string清洗
                    if isinstance(data.get("desc"), list):
                        data["desc"] = ", ".join(data["desc"])
                    results.append(data)
                
                # 2. 搜食材 (补位)
                if len(results) < limit:
                    ret_i = session.run(cypher_ing, kw=keyword, limit=limit - len(results))
                    for record in ret_i:
                        data = record.data()
                        data["cal"] = None
                        results.append(data)

            except Exception as e:
                print(f"[KG Search Error] {e}")

        # 如果还是搜不到，可能就是真的没有这个菜（Translation mismatch），
        # 但至少不会再报 property missing 的警告了。
        if not results:
            print(f"[DietKG] ⚠️ 关键词 '{keyword}' 搜索结果为空 (Schema 已确认无误)")
            # 可以在这里做个兜底，比如搜不到全名就拆词搜，或者直接返回空让 DietLogger 估算
            
        return results
    def get_recipe_full_detail_by_name(
        self,
        recipe_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        根据 recipe_name 获取：
        - recipe 基本信息
        - ingredients（含用量、单位、weight、text）
        - nutrients（含 label / name / quantity / unit）

        返回的数据结构可直接用于饮食推荐与内容生成
        """

        cypher = """
        MATCH (r:Recipe {recipe_name: $recipe_name})

        OPTIONAL MATCH (r)-[:HAS_INGREDIENT]->(i:Ingredient)
        OPTIONAL MATCH (r)-[:HAS_NUTRIENT]->(n:Nutrient)

        RETURN
            r {
                .*,
                ingredients: collect(
                    DISTINCT {
                        name: i.name,
                        quantity: i.quantity,
                        measure: i.measure,
                        weight: i.weight,
                        text: i.text
                    }
                ),
                nutrients: collect(
                    DISTINCT {
                        label: n.label,
                        name: n.name,
                        quantity: n.quantity,
                        unit: n.unit
                    }
                )
            } AS recipe
        """

        with self.driver.session() as session:
            record = session.run(
                cypher,
                recipe_name=recipe_name
            ).single()

        if not record:
            return None

        recipe = record["recipe"]

        # ---------- 安全清洗（None / 空节点） ----------
        recipe["ingredients"] = [
            i for i in recipe.get("ingredients", [])
            if i.get("name")
        ]

        recipe["nutrients"] = [
            n for n in recipe.get("nutrients", [])
            if n.get("name")
        ]

        return recipe