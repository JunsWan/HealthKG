# code/tools/diet_evaluator.py

from typing import List, Dict, Any
from itertools import combinations
from datetime import datetime, timedelta
import math
from query import *
from collections import defaultdict
import time
import numpy


MEAL_RATIOS = {
    "breakfast": 0.25,
    "lunch": 0.35,
    "dinner": 0.30,
    "snack": 0.10,
    "brunch": 0.30
}

ACTIVITY_FACTOR = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "high": 1.725,
    "extreme": 1.9
}


def compute_tdee(user):
    # 计算每日静止能量需求
    if user["demographics"]["gender"] == "male":
        bmr = (
            10 * user["demographics"]["weight_kg"]
            + 6.25 * user["demographics"]["height_cm"]
            - 5 * user["demographics"]["age"]
            + 5
        )
    else:
        bmr = (
            10 * user["demographics"]["weight_kg"]
            + 6.25 * user["demographics"]["height_cm"]
            - 5 * user["demographics"]["age"]
            - 161
        )
    tdee = bmr * ACTIVITY_FACTOR[user["activity"]["activity_level"]]
    goal = user["activity"].get("user_goal", "maintenance")
    if goal == "bulking":
        tdee *= 1.12
    elif goal == "cutting":
        tdee *= 0.85

    return tdee


def remaining_calories_today(user, tdee):
    eaten = sum(
        m.get("calories", 0)
        for m in user["current_context"].get("today_intake", [])
        if m.get("status") != "skipped"
    )
    return max(tdee - eaten, 0)


def ingredient_score(recipe, user):
    score = 0.0
    ingredients_text = str(recipe.get("ingredients", "")).lower()

    for ing in user["diet_profile"].get("preferred_ingredients", []):
        if ing.lower() in ingredients_text:
            score += 0.05

    for ing in user["diet_profile"].get("disliked_ingredients", []):
        if ing.lower() in ingredients_text:
            score -= 0.10

    return score


def history_penalty(recipe_names, history):
    now = datetime.now()
    penalty = 0.0

    for h in history:
        if h["recipe_name"] not in recipe_names:
            continue
        t = datetime.fromisoformat(h["timestamp"])
        days = (now - t).days
        penalty += 1.0 / max(days + 1, 1)

    return penalty


def normalize_nutrients(nutrients):
    """
    将 nutrient list 转为 dict:
    - key: nutrient name（如 carbs, protein）
    - value: quantity（float）

    原则：
    - 缺失 / 非法 quantity -> 直接跳过
    - 不强行补 0，避免误导推荐与生成
    """
    if not nutrients:
        return {}

    result = {}

    for n in nutrients:
        if not isinstance(n, dict):
            continue

        # 使用 name（如 CHOCDF / PROCNT）或 label（如 Carbs）
        raw_key = n.get("name") or n.get("label")
        if not raw_key:
            continue

        try:
            quantity = float(n.get("quantity"))
        except (TypeError, ValueError):
            continue  # ❗️关键：直接跳过，而不是置 0

        clean_key = (
            str(raw_key)
            .lower()
            .strip()
            .replace(" ", "_")
            .replace("-", "_")
        )

        result[clean_key] = round(quantity, 2)

    return result


def normalize_ingredients(ingredients):
    """
    ingredient 规范化：
    - 不伪造 quantity
    - 保留 text 以供 LLM 生成使用
    """
    if not ingredients:
        return []

    normalized = []

    for i in ingredients:
        if not isinstance(i, dict):
            continue

        name = i.get("name")
        if not name:
            continue

        normalized.append({
            "name": name,
            "quantity": i.get("quantity"),          # 允许 None
            "measure": i.get("measure") or "",
            "weight_g": round(i.get("weight") or 0, 1),
            "text": i.get("text") or ""
        })

    return normalized



def recommend_meals(user, kg: "DietKGQuery", top_k=3):
    start_time = time.time()
    tdee = compute_tdee(user)
    meal = user["current_context"]["meal_time"]

    if user["current_context"]["today_intake"]:
        remaining = remaining_calories_today(user, tdee)
        if meal == "breakfast":
            target_cal = remaining * 0.25
        elif meal == "lunch" or meal == "brunch": 
            target_cal = remaining * 0.55
        elif meal == "dinner":
            target_cal = remaining 
        else:
            target_cal = remaining * MEAL_RATIOS.get(meal, 0.1)
    else:
        target_cal = tdee * MEAL_RATIOS.get(meal, 0.3)


    dish_constraint = {
        "breakfast": ["bread", "egg", "cereals"],
        "lunch": ["main course", "salad", "soup"],
        "dinner": ["main course", "salad", "soup"],
        "snack": ["snack", "desserts", "drinks"],
        "brunch": ["main course", "salad"]
    }

    candidates = kg.fetch_candidates_with_detail(
        meal_type=meal if meal != "lunch" else "lunch/dinner",
        dish_types=dish_constraint[meal],
        diet_labels=user["diet_profile"]["diet_labels"],
        health_labels=user["diet_profile"]["health_preferences"],
        forbidden_cautions=user["diet_profile"]["forbidden_cautions"]
    )
    print("符合条件的候选数量有：", len(candidates))
    candidates_time = time.time()
    print("搜索到候选的时间为：", candidates_time-start_time)
    meals = []
    for k in (1, 2, 3):
        for combo in combinations(candidates, k):
            total_cal = sum(
                r["calories"] / max(r["servings"], 1)
                for r in combo
            )

            score = 0.0

            # 热量匹配
            score += max(
                0, 1 - abs(total_cal - target_cal) / max(target_cal, 1)
            ) * 0.8

            # 蛋白偏好（增肌）
            if user["activity"].get("user_goal") == "bulking":
                score += sum(
                    "High-Protein" in r.get("diet_labels", [])
                    for r in combo
                ) * 0.2

            # 健康标签
            score += sum(
                len(set(r["health_labels"]) & set(user["diet_profile"]["health_preferences"]))
                for r in combo
            ) * 0.2

            # 中国菜偏好
            nationality = user["demographics"].get("nationality", "chinese")
            score += sum(
                1 for r in combo
                if nationality in r["cuisine_type"]
            ) * 0.1

            # 历史惩罚
            score -= history_penalty(
                [r["recipe_name"] for r in combo],
                user["history"]
            ) * 0.15

            
            plan_recipes = []
            plan_nutrients = defaultdict(float)

            for r in combo:
                per_serving_factor = 1.0 / max(r["servings"], 1)
                nutrients = normalize_nutrients(r["nutrients"])
                for k2, v2 in nutrients.items():
                    plan_nutrients[k2] += v2 * per_serving_factor

                plan_recipes.append({
                    "recipe_name": r["recipe_name"],
                    "servings_used_ratio": per_serving_factor,
                    "calories": round(r["calories"] * per_serving_factor, 1),
                    "cuisine_type": r["cuisine_type"],
                    "dish_type": r["dish_type"],
                    "ingredients": normalize_ingredients(r["ingredients"]),
                    "nutrients": nutrients
                })

            meals.append({
                "meal_time": meal,
                "target_calories": round(target_cal, 1),
                "actual_calories": round(total_cal, 1),
                "score": round(score, 3),
                "recipes": plan_recipes,
            })

    meals.sort(key=lambda x: x["score"], reverse=True)
    end_time = time.time()
    print("全部评分完的时间为：", end_time-start_time)
    return meals[:top_k]
