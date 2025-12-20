下面给你整理一份 **饮食推荐模块（Diet Recommender）的完整 Markdown 文档说明**，涵盖代码结构、输入输出格式、字段说明、评分逻辑等内容，便于你开发或对接 LLM 模块使用。

---

# Diet Recommender 模块说明

## 1. 模块概览

Diet Recommender 模块主要功能是基于 **用户身体数据、饮食偏好、历史饮食记录**，从 Neo4j 知识图谱（Diet KG）中检索候选食谱，计算分数并生成推荐组合。

主要文件和函数：

| 文件                    | 主要功能                                                                                           |
| --------------------- | ---------------------------------------------------------------------------------------------- |
| `diet_recommender.py` | MAS 工具封装接口，接收用户信息，调用 evaluator 生成排序后的饮食方案                                                      |
| `diet_evaluator.py`   | 核心计算逻辑：候选食谱评分、组合生成、热量匹配、健康标签加分、历史惩罚                                                            |
| `query.py`            | Neo4j 查询接口，`DietKGQuery` 提供 `fetch_candidates_with_detail` 获取候选食谱及 ingredients、nutrients 等详细信息 |

推荐流程：

```
用户信息 → diet_recommendation_tool(args) → recommend_meals(user, kg) → fetch_candidates_with_detail → 评分排序 → 返回 top_k 推荐
```

---

## 2. 输入数据格式

`diet_recommendation_tool` 接收一个字典 `args`，典型格式如下：

```json
{
  "user_id": "u123456",
  "demographics": {
    "gender": "female",
    "age": 30,
    "height_cm": 165.0,
    "weight_kg": 60.0,
    "nationality": "chinese"
  },
  "activity": {
    "activity_level": "moderate",
    "user_goal": "bulking"
  },
  "diet_profile": {
    "diet_labels": ["Low-Carb", "High-Fiber"],          # "Low-Carb", "High-Fiber", "Low-Sodium", "Low-Fat", "Balanced", "High-Protein"
    "health_preferences": ["Vegetarian", "Dairy-Free"],  # Tree-Nut-Free, Peanut-Free, Shellfish-Free, Fish-Free, Egg-Free, Dairy-Free, Soy-Free, Vegetarian, Gluten-Free, Vegan, Paleo, Low Sugar
    "forbidden_cautions": ["Gluten", "Sulfites"],      #  Sulfites, Wheat, Gluten, FODMAP, Tree-Nuts, Shellfish, Soy, Milk, Eggs
    "preferred_ingredients": ["tofu", "broccoli"],
    "disliked_ingredients": ["beef", "pork"]
  },
  "current_context": {
    "meal_time": "dinner",
    "today_intake": [
      {
        "meal_time": "breakfast",
        "recipes": [
          {"recipe_name": "Oatmeal with Nuts", "servings_used": 1}
        ],
        "calories": 380,
        "timestamp": "2025-12-20T08:10:00"
      }
    ]
  },
  "history": [
    {
      "meal_time": "lunch",
      "recipes": [{"recipe_name": "Stir-fried Tofu", "servings_used": 0.5}],
      "calories": 520,
      "timestamp": "2025-12-19T12:30:00"
    }
  ]
}
```

### 字段说明

| 字段                      | 类型         | 说明                      |         |              |       |          |
| ----------------------- | ---------- | ----------------------- | ------- | ------------ | ----- | -------- |
| `user_id`               | str        | 用户唯一标识                  |         |              |       |          |
| `demographics`          | dict       | 用户身体及基本信息               |         |              |       |          |
| `gender`                | str        | `male` / `female`       |         |              |       |          |
| `age`                   | int        | 年龄（岁）                   |         |              |       |          |
| `height_cm`             | float      | 身高（厘米）                  |         |              |       |          |
| `weight_kg`             | float      | 体重（公斤）                  |         |              |       |          |
| `nationality`           | str        | 国籍，用于本土菜加权              |         |              |       |          |
| `activity`              | dict       | 当日运动水平及目标               |         |              |       |          |
| `activity_level`        | str        | `sedentary              | light   | moderate     | high  | extreme` |
| `user_goal`             | str        | `bulking                | cutting | maintenance` |       |          |
| `diet_profile`          | dict       | 饮食相关偏好与禁忌               |         |              |       |          |
| `diet_labels`           | list[str]  | 饮食标签加分，如 `Low-Carb`     |         |              |       |          |
| `health_preferences`    | list[str]  | 健康相关标签加分，如 `Vegetarian` |         |              |       |          |
| `forbidden_cautions`    | list[str]  | 不允许出现的成分，如 `Gluten`     |         |              |       |          |
| `preferred_ingredients` | list[str]  | 用户喜欢的食材，加分              |         |              |       |          |
| `disliked_ingredients`  | list[str]  | 用户不喜欢的食材，减分             |         |              |       |          |
| `current_context`       | dict       | 当餐信息，包含时间和已吃食谱          |         |              |       |          |
| `meal_time`             | str        | 当前餐类型，如 `breakfast      | lunch   | dinner       | snack | brunch`  |
| `today_intake`          | list[dict] | 当日已摄入记录，后续用于计算剩余热量（没有也或不完整也可以）      |         |              |       |          |
| `history`               | list[dict] | 历史饮食记录，用于历史惩罚, today_intake会被记录到history中           |         |              |       |          |

---

## 3. 输出数据格式

函数返回 **列表**，每个元素为一餐推荐组合：

```json
[
  {
    "meal_time": "dinner",
    "target_calories": 709.2,
    "actual_calories": 476.8,
    "score": 1.738,
    "recipes": [
      {
        "recipe_name": "Crisp-skinned thai chilli snapper",
        "servings_used": 0.25,
        "calories": 325.1,
        "cuisine_type": ["south east asian"],
        "dish_type": ["starter", "main course"],
        "ingredients": [
          {"name": "fish", "quantity": 200, "measure": "g", "weight_g": 200.0, "text": "200g fish"},
          {"name": "oil", "quantity": 1, "measure": "tbsp", "weight_g": 14.0, "text": "1 tbsp oil"}
        ],
        "nutrients": [
          {"name": "CHOCDF", "label": "Carbs", "quantity": 20.5, "unit": "g"},
          {"name": "PROCNT", "label": "Protein", "quantity": 30.0, "unit": "g"}
        ]
      },
    ]
  },
]
```

### 字段说明

| 字段                | 类型         | 说明                              |
| ----------------- | ---------- | ------------------------------- |
| `meal_time`       | str        | 餐次                              |
| `target_calories` | float      | 计算出的目标摄入热量                      |
| `actual_calories` | float      | 当前组合食谱实际热量总和                    |
| `score`           | float      | 综合评分，用于排序                       |
| `recipes`         | list[dict] | 食谱列表，每个字典包含详细信息                 |
| `recipe_name`     | str        | 食谱名称                            |
| `servings_used`   | float      | 当前推荐组合中使用的份数                    |
| `calories`        | float      | 对应份数的热量                         |
| `cuisine_type`    | list[str]  | 菜系                              |
| `dish_type`       | list[str]  | 菜品类型                            |
| `ingredients`     | list[dict] | 食材列表（含数量、单位、重量、描述）              |
| `nutrients`       | list[dict] | 对应食材营养信息（含 label、quantity、unit） |

---

## 4. 核心函数与逻辑

### 4.1 `diet_recommendation_tool(args) -> List[Dict]`

* MAS 工具接口
* 接收用户信息字典 `args`
* 调用 `recommend_meals(user, kg)` 获取候选组合并评分
* 返回排序后的 top 3 推荐组合

---

### 4.2 `recommend_meals(user, kg, top_k=3)`

核心逻辑：

1. **热量计算**

   * 使用 `compute_tdee(user)` 计算用户理论每日能量需求
   * 根据 `meal_time` 和 `today_intake` 动态计算本餐目标热量
2. **Neo4j 查询**

   * 调用 `DietKGQuery.fetch_candidates_with_detail` 获取候选食谱
   * 硬约束过滤：

     * `meal_type` 与 `dish_type` 匹配
     * 不含用户禁忌成分 (`forbidden_cautions`)
   * 返回食谱详细信息，包括 ingredients 和 nutrients
3. **评分规则**

   * 热量匹配度（target_calories vs 组合总热量） → 权重 0.3
   * 蛋白偏好（增肌用户） → 权重 0.2
   * 健康标签匹配 → 权重 0.15
   * 国籍/本土菜加分 → 权重 0.1
   * 历史重复惩罚 → 权重 0.15
   * 用户偏好食材加分，讨厌食材减分
4. **组合生成**

   * 组合 1~3 个食谱，计算组合总热量和分数
   * 返回前 top_k 个组合

---

### 4.3 `DietKGQuery.fetch_candidates_with_detail(...)`

* 从 Neo4j KG 获取食谱及其关联数据
* 返回字段：

  * `id`, `recipe_name`, `calories`, `servings`
  * `cuisine_type`, `meal_type`, `dish_type`
  * `ingredients`（每个 ingredient 的 name, quantity, measure, weight_g, text）
  * `nutrients`（label, quantity, unit）

---
### 4.4 `DietKGQuery.et_recipe_full_detail_by_name(...)`

* 从 Neo4j KG 依据食谱名字获取食谱及其关联数据
* 返回字段：

  * `id`, `recipe_name`, `calories`, `servings`
  * `cuisine_type`, `meal_type`, `dish_type`
  * `ingredients`（每个 ingredient 的 name, quantity, measure, weight_g, text）
  * `nutrients`（label, quantity, unit）

---

## 5. 注意事项与扩展

* 每餐可以推荐多道菜品（组合逻辑在 `recommend_meals` 中）
* 可动态调整热量占比，考虑当天已摄入
* 用户偏好、历史饮食会影响推荐权重
* ingredient 和 nutrient 信息完整，便于 LLM 生成个性化文本或食谱建议
* 未来可扩展：

  * 微量元素平衡优化
  * 过敏成分严格过滤
  * 不同国籍菜系偏好权重调整

---

## 6. 调用示例

详细参考demo.py