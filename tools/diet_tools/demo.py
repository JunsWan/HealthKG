# main.py

from tools.diet_tools.query import DietKGQuery
from tools.diet_tools.diet_recommender import diet_recommendation_tool

user = {
  "user_id": "user_001",
  "demographics": {
    "gender": "male",
    "age": 29,
    "height_cm": 175,
    "weight_kg": 82,
    "nationality": "chinese"
  },
  "activity": {
    "activity_level": "sedentary",
    "user_goal": "cutting"
  },
  "diet_profile": {
    "diet_labels": ["Low-Fat", "Low-Carb"],
    "health_preferences": ["Gluten-Free", "Dairy-Free"],
    "forbidden_cautions": ["Shellfish"],
    "preferred_ingredients": ["chicken", "broccoli", "tofu"],
    "disliked_ingredients": ["cilantro"]
  },
  "current_context": {
    "meal_time": "dinner",
    "today_intake": [
      {
        "meal_time": "breakfast",
        "calories": 380,
        "timestamp": "2025-12-20T08:10:00"
      },
      {
        "meal_time": "lunch",
        "calories": 720,
        "timestamp": "2025-12-20T12:30:00"
      }
    ]
  },
  "history": [
    {
      "recipe_name": "Fried Chicken Banh Mi",
      "timestamp": "2025-12-18T19:00:00"
    }
  ]
}


meals = diet_recommendation_tool(user)
print(meals)
for i, p in enumerate(meals, 1):
    print(f"\n方案 {i} | 得分 {p['score']}")
    print("目标热量:", p["target_calories"])
    print("实际热量:", p["actual_calories"])
    for r in p["recipes"]:
        print(" -", r["recipe_name"], r["calories"], "kcal")

