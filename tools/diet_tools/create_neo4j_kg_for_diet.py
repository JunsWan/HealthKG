from neo4j import GraphDatabase
import pandas as pd
import json
from tqdm import tqdm
import ast
from math import ceil

# ============================================================
# Neo4j Config
# ============================================================
URI = "your neo4j url"
AUTH = ("neo4j", "password")
CSV_FILE = "./data/DietKG/DATA/chinese_recipes.csv"
BATCH_SIZE = 100  # 可以调整

# ============================================================
# CSV 解析
# ============================================================
def parse_list_column(x):
    try:
        return json.loads(x.replace("'", '"'))
    except:
        try:
            return ast.literal_eval(x)
        except:
            return []

def parse_dict_column(x):
    try:
        return json.loads(x)
    except:
        try:
            return ast.literal_eval(x)
        except:
            return {}

df = pd.read_csv(CSV_FILE)
df['ingredients'] = df['ingredients'].apply(parse_list_column)
df['total_nutrients'] = df['total_nutrients'].apply(parse_dict_column)
df['daily_values'] = df['daily_values'].apply(parse_dict_column)

driver = GraphDatabase.driver(URI, auth=AUTH)

# ============================================================
# 批量插入函数
# ============================================================
def batch(iterable, n=1):
    l = len(iterable)
    for i in range(0, l, n):
        yield iterable[i:i+n]

def load_recipes_to_neo4j(df, batch_size=BATCH_SIZE):
    # 1️⃣ Recipe 节点
    recipes_data = []
    for _, row in df.iterrows():
        recipes_data.append({
            "label": row['label'],
            "name": row['recipe_name'],
            "servings": row['servings'],
            "calories": row['calories'],
            "total_weight_g": row['total_weight_g'],
            "image_url": row['image_url'],
            "diet_labels": str(row['diet_labels']),
            "health_labels": str(row['health_labels']),
            "cautions": str(row['cautions']),
            "cuisine_type": str(row['cuisine_type']),
            "meal_type": str(row['meal_type']),
            "dish_type": str(row['dish_type'])
        })

    with driver.session() as session:
        for r_batch in tqdm(list(batch(recipes_data, batch_size)), desc="Importing Recipes"):
            session.run("""
                UNWIND $batch AS r
                MERGE (recipe:Recipe {label: r.label})
                SET recipe += r
            """, batch=r_batch)

    # 2️⃣ Ingredient 节点 + HAS_INGREDIENT
    ingredient_nodes = {}
    ingredient_rels = []

    for _, row in df.iterrows():
        for ing in row["ingredients"]:
            name = ing.get("food")
            if not name:
                continue

            ingredient_nodes[name] = {"name": name}

            ingredient_rels.append({
                "recipe_label": row["label"],
                "ingredient_name": name,
                "quantity": ing.get("quantity"),
                "measure": ing.get("measure"),
                "weight": ing.get("weight"),
                "text": ing.get("text")
            })

    with driver.session() as session:
        for b in tqdm(list(batch(list(ingredient_nodes.values()), batch_size)), desc="Importing Ingredients"):
            session.run("""
                UNWIND $batch AS i
                MERGE (:Ingredient {name: i.name})
            """, batch=b)

        for b in tqdm(list(batch(ingredient_rels, batch_size)), desc="Creating USES relations"):
            session.run("""
                UNWIND $batch AS r
                MATCH (rec:Recipe {label: r.recipe_label})
                MATCH (ing:Ingredient {name: r.ingredient_name})
                MERGE (rec)-[rel:USES]->(ing)
                SET rel.quantity = r.quantity,
                    rel.measure = r.measure,
                    rel.weight = r.weight,
                    rel.text = r.text
            """, batch=b)


    # 3️⃣ Nutrient 节点 + HAS_NUTRIENT
    nutrient_nodes = {}
    nutrient_rels = []

    for _, row in df.iterrows():
        for name, val in row["total_nutrients"].items():
            nutrient_nodes[name] = {
                "name": name,
                "unit": val.get("unit"),
                "label": val.get("label")
            }
            nutrient_rels.append({
                "recipe_label": row["label"],
                "nutrient_name": name,
                "quantity": val.get("quantity")
            })

    with driver.session() as session:
        for b in tqdm(list(batch(list(nutrient_nodes.values()), batch_size)), desc="Importing Nutrients"):
            session.run("""
                UNWIND $batch AS n
                MERGE (nut:Nutrient {name: n.name})
                SET nut.unit = n.unit,
                    nut.label = n.label
            """, batch=b)

        for b in tqdm(list(batch(nutrient_rels, batch_size)), desc="Creating HAS_NUTRIENT relations"):
            session.run("""
                UNWIND $batch AS r
                MATCH (rec:Recipe {label: r.recipe_label})
                MATCH (nut:Nutrient {name: r.nutrient_name})
                MERGE (rec)-[rel:HAS_NUTRIENT]->(nut)
                SET rel.quantity = r.quantity
            """, batch=b)

    # 4️⃣ DailyValue 节点 + HAS_DAILY_VALUE
    dv_nodes = {}
    dv_rels = []

    for _, row in df.iterrows():
        for name, val in row["daily_values"].items():
            dv_nodes[name] = {
                "name": name,
                "unit": val.get("unit"),
                "label": val.get("label")
            }
            dv_rels.append({
                "recipe_label": row["label"],
                "dv_name": name,
                "quantity": val.get("quantity")
            })

    with driver.session() as session:
        for b in tqdm(list(batch(list(dv_nodes.values()), batch_size)), desc="Importing DailyValues"):
            session.run("""
                UNWIND $batch AS d
                MERGE (dv:DailyValue {name: d.name})
                SET dv.unit = d.unit,
                    dv.label = d.label
            """, batch=b)

        for b in tqdm(list(batch(dv_rels, batch_size)), desc="Creating HAS_DAILY_VALUE relations"):
            session.run("""
                UNWIND $batch AS r
                MATCH (rec:Recipe {label: r.recipe_label})
                MATCH (dv:DailyValue {name: r.dv_name})
                MERGE (rec)-[rel:HAS_DAILY_VALUE]->(dv)
                SET rel.quantity = r.quantity
            """, batch=b)

    print("✅ Finished loading all data into Neo4j")

# ============================================================
# 执行导入
# ============================================================
load_recipes_to_neo4j(df)
