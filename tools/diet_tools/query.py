# /tools/diet_tools/query.py

from neo4j import GraphDatabase
from typing import Dict, Any, Optional

class DietKGQuery:

    def __init__(self, uri, auth):
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