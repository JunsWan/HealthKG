import pandas as pd
import ast
# 参数
input_csv = "../DATA/recipes.csv"
output_csv = "../DATA/chinese_recipes.csv"
column_name = "cuisine_type"      # 需要检查的列名

target_cuisines = [
    "asian",
    "chinese",
    "indian",
    "south east asian",
    "japanese",
    "korean"
]     # 要匹配的内容

# 读取 CSV
df = pd.read_csv(input_csv)


# ========== 删除第一列 ==========
# 通常是 unnamed index
df = df.iloc[:, 1:]

old_second_col = df.columns[0]
df = df.rename(columns={old_second_col: "label"})

df["cuisine_type"] = df["cuisine_type"].apply(
    lambda x: ast.literal_eval(x) if pd.notna(x) else []
)
cuisine_counts = (
    df.explode("cuisine_type")
      .value_counts("cuisine_type")
)

print("各 cuisine_type 数量统计：")
print(cuisine_counts)

# ========== 过滤指定 cuisine_type ==========
filtered_df = df[
    df["cuisine_type"].apply(
        lambda cuisines: any(c in target_cuisines for c in cuisines)
    )
]

# ========== 保存新 CSV ==========
filtered_df.to_csv(output_csv, index=False, encoding="utf-8-sig")

print(f"\n已保存 {len(filtered_df)} 条数据到 {output_csv}")