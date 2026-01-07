from neo4j import GraphDatabase
from typing import Dict, Any, Optional


class DietKGQuery:

    def __init__(self, uri, auth):
        masked_uri = uri
        print(f"[DietKGQuery] Connecting to: {masked_uri} ...")
        self.driver = GraphDatabase.driver(uri, auth=auth)

    def close(self):
        self.driver.close()

    # =====================================================
    # 1️⃣ 基础候选（只返回 Recipe 本身，不碰 ingredient）
    # =====================================================
    def fetch_candidates(
        self,
        meal_type: str,
        dish_types: list,
        diet_labels: list,
        health_labels: list,
        forbidden_cautions: list
    ):
        """
        KG 只做硬约束过滤（不展开关系）
        """

        query = """
        MATCH (r:Recipe)
        WHERE
          r.meal_type CONTAINS $meal_type
          AND ANY(dt IN $dish_types WHERE r.dish_type CONTAINS dt)

          AND (
            size($diet_labels) = 0
            OR ALL(dl IN $diet_labels WHERE r.diet_labels CONTAINS dl)
          )

          AND (
            size($forbidden_cautions) = 0
            OR NONE(fc IN $forbidden_cautions WHERE r.cautions CONTAINS fc)
          )

        RETURN
          r.label           AS recipe_id,
          r.name            AS recipe_name,
          r.calories        AS calories,
          r.servings        AS servings,
          r.cuisine_type    AS cuisine_type,
          r.meal_type       AS meal_type,
          r.dish_type       AS dish_type,
          r.diet_labels     AS diet_labels,
          r.health_labels   AS health_labels
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

    # =====================================================
    # 2️⃣ 带 Ingredient / Nutrient / DailyValue 的完整展开
    # =====================================================
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
        Recipe + USES(ingredient) + HAS_NUTRIENT + HAS_DAILY_VALUE
        """

        query = """
        MATCH (r:Recipe)
        WHERE
          r.meal_type CONTAINS $meal_type
          AND ANY(dt IN $dish_types WHERE r.dish_type CONTAINS dt)

          AND (
            size($diet_labels) = 0
            OR ALL(dl IN $diet_labels WHERE r.diet_labels CONTAINS dl)
          )

          AND (
            size($forbidden_cautions) = 0
            OR NONE(fc IN $forbidden_cautions WHERE r.cautions CONTAINS fc)
          )

        OPTIONAL MATCH (r)-[u:USES]->(ing:Ingredient)
        OPTIONAL MATCH (r)-[hn:HAS_NUTRIENT]->(nut:Nutrient)
        OPTIONAL MATCH (r)-[hd:HAS_DAILY_VALUE]->(dv:DailyValue)

        RETURN
          r.label           AS recipe_id,
          r.name            AS recipe_name,
          r.servings        AS servings,
          r.calories        AS calories,
          r.cuisine_type    AS cuisine_type,
          r.meal_type       AS meal_type,
          r.dish_type       AS dish_type,
          r.diet_labels     AS diet_labels,
          r.health_labels   AS health_labels,

          collect(
            DISTINCT {
              name: ing.name,
              quantity: u.quantity,
              measure: u.measure,
              weight: u.weight,
              text: u.text
            }
          ) AS ingredients,

          collect(
            DISTINCT {
              name: nut.name,
              label: nut.label,
              unit: nut.unit,
              quantity: hn.quantity
            }
          ) AS nutrients,

          collect(
            DISTINCT {
              name: dv.name,
              label: dv.label,
              unit: dv.unit,
              quantity: hd.quantity
            }
          ) AS daily_values
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
            return [r.data() for r in result]

    # =====================================================
    # 3️⃣ 按菜名精确获取完整 Recipe（✔ schema 对齐）
    # =====================================================
    def get_recipe_full_detail_by_name(
        self,
        recipe_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        单个 Recipe 的完整信息
        """

        cypher = """
        MATCH (r:Recipe {name: $recipe_name})

        OPTIONAL MATCH (r)-[u:USES]->(ing:Ingredient)
        OPTIONAL MATCH (r)-[hn:HAS_NUTRIENT]->(nut:Nutrient)
        OPTIONAL MATCH (r)-[hd:HAS_DAILY_VALUE]->(dv:DailyValue)

        RETURN
          r {
            .*,
            ingredients: collect(
              DISTINCT {
                name: ing.name,
                quantity: u.quantity,
                measure: u.measure,
                weight: u.weight,
                text: u.text
              }
            ),
            nutrients: collect(
              DISTINCT {
                name: nut.name,
                label: nut.label,
                unit: nut.unit,
                quantity: hn.quantity
              }
            ),
            daily_values: collect(
              DISTINCT {
                name: dv.name,
                label: dv.label,
                unit: dv.unit,
                quantity: hd.quantity
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

        # 安全清洗
        recipe["ingredients"] = [i for i in recipe["ingredients"] if i.get("name")]
        recipe["nutrients"] = [n for n in recipe["nutrients"] if n.get("name")]
        recipe["daily_values"] = [d for d in recipe["daily_values"] if d.get("name")]

        return recipe
