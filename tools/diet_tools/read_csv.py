import pandas as pd
import ast
from collections import Counter
from tqdm import tqdm

CSV_FILE = "./data/DietKG/DATA/chinese_recipes.csv"

TARGET_COLUMNS = [
    "diet_labels",
    "health_labels",
    "cautions",
    "cuisine_type",
    "meal_type",
    "dish_type"
]

# ============================================================
# 安全解析 str(list)
# ============================================================
def parse_str_list(x):
    """
    将形如 "['A', 'B']" / '["A","B"]' 的字符串解析为 list
    """
    if pd.isna(x):
        return []
    if isinstance(x, list):
        return x
    try:
        return ast.literal_eval(x)
    except Exception:
        return []

# ============================================================
# 主逻辑
# ============================================================
def count_list_fields(csv_file):
    df = pd.read_csv(csv_file)

    results = {}

    for col in TARGET_COLUMNS:
        counter = Counter()

        for val in tqdm(df[col], desc=f"Counting {col}"):
            items = parse_str_list(val)
            for item in set(items):  # ✅ 去重后统计
                counter[item] += 1

        results[col] = counter

    return results

# ============================================================
# 执行
# ============================================================
counts = count_list_fields(CSV_FILE)

# ============================================================
# 输出结果
# ============================================================
for col, counter in counts.items():
    print(f"\n===== {col} =====")
    for k, v in counter.most_common():
        print(f"{k}: {v}")
