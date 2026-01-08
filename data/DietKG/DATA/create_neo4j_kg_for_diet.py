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
CSV_FILE = "chinese_recipes.csv"
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
    ingredient_map = {}  # 去重
    rel_ing = []
    for _, row in df.iterrows():
        recipe_label = row['label']
        for ing in row['ingredients']:
            name = ing.get("food")
            if name not in ingredient_map:
                ingredient_map[name] = {
                    "name": name,
                    "text": ing.get("text"),
                    "weight": ing.get("weight"),
                    "measure": ing.get("measure"),
                    "quantity": ing.get("quantity")
                }
            rel_ing.append({"recipe_label": recipe_label, "ingredient_name": name})

    ingredients_data = list(ingredient_map.values())
    with driver.session() as session:
        for i_batch in tqdm(list(batch(ingredients_data, batch_size)), desc="Importing Ingredients"):
            session.run("""
                UNWIND $batch AS i
                MERGE (ing:Ingredient {name: i.name})
                SET ing += i
            """, batch=i_batch)

        for r_batch in tqdm(list(batch(rel_ing, batch_size)), desc="Creating HAS_INGREDIENT Relations"):
            session.run("""
                UNWIND $batch AS rel
                MATCH (r:Recipe {label: rel.recipe_label})
                MATCH (i:Ingredient {name: rel.ingredient_name})
                MERGE (r)-[:HAS_INGREDIENT]->(i)
            """, batch=r_batch)

    # 3️⃣ Nutrient 节点 + HAS_NUTRIENT
    nutrient_map = {}
    rel_nut = []
    for _, row in df.iterrows():
        recipe_label = row['label']
        for nut_name, nut_val in row['total_nutrients'].items():
            if nut_name not in nutrient_map:
                nutrient_map[nut_name] = {
                    "name": nut_name,
                    "unit": nut_val.get("unit"),
                    "label": nut_val.get("label"),
                    "quantity": nut_val.get("quantity")
                }
            rel_nut.append({"recipe_label": recipe_label, "nutrient_name": nut_name})

    nutrients_data = list(nutrient_map.values())
    with driver.session() as session:
        for n_batch in tqdm(list(batch(nutrients_data, batch_size)), desc="Importing Nutrients"):
            session.run("""
                UNWIND $batch AS n
                MERGE (nut:Nutrient {name: n.name})
                SET nut += n
            """, batch=n_batch)

        for r_batch in tqdm(list(batch(rel_nut, batch_size)), desc="Creating HAS_NUTRIENT Relations"):
            session.run("""
                UNWIND $batch AS rel
                MATCH (r:Recipe {label: rel.recipe_label})
                MATCH (n:Nutrient {name: rel.nutrient_name})
                MERGE (r)-[:HAS_NUTRIENT]->(n)
            """, batch=r_batch)

    # 4️⃣ DailyValue 节点 + HAS_DAILY_VALUE
    dv_map = {}
    rel_dv = []
    for _, row in df.iterrows():
        recipe_label = row['label']
        for dv_name, dv_val in row['daily_values'].items():
            if dv_name not in dv_map:
                dv_map[dv_name] = {
                    "name": dv_name,
                    "unit": dv_val.get("unit"),
                    "label": dv_val.get("label"),
                    "quantity": dv_val.get("quantity")
                }
            rel_dv.append({"recipe_label": recipe_label, "dv_name": dv_name})

    dv_data = list(dv_map.values())
    with driver.session() as session:
        for d_batch in tqdm(list(batch(dv_data, batch_size)), desc="Importing DailyValues"):
            session.run("""
                UNWIND $batch AS d
                MERGE (dv:DailyValue {name: d.name})
                SET dv += d
            """, batch=d_batch)

        for r_batch in tqdm(list(batch(rel_dv, batch_size)), desc="Creating HAS_DAILY_VALUE Relations"):
            session.run("""
                UNWIND $batch AS rel
                MATCH (r:Recipe {label: rel.recipe_label})
                MATCH (dv:DailyValue {name: rel.dv_name})
                MERGE (r)-[:HAS_DAILY_VALUE]->(dv)
            """, batch=r_batch)

    print("Finished loading all data to Neo4j!")

# ============================================================
# 执行导入
# ============================================================
load_recipes_to_neo4j(df)
