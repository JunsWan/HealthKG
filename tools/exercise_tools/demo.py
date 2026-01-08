# demo.py

from recommender_exrx import recommend_exercises
from query import ExerciseKGQuery

URI = "your neo4j url"
AUTH = ("neo4j", "password")

user_profile = {
    "target_body_part": "Chest",
    "injury_body_part": ["Waist"],
    "available_equipment": ["Barbell", "Dumbbell", "Cable", "Smith", "Lever"],
    "history": [
  {
    "id": "Retraction__Neck__Stretch__",
    "timestamp": "2025-12-08T21:48:31",
    "body_part": "Neck",
    "target_muscles": [
      "Rhomboids",
      "Obliques"
    ]
  },
  {
    "id": "Wall Rear Neck Bridge__Neck__Body Weight__Splenius",
    "timestamp": "2025-12-03T18:34:34",
    "body_part": "Neck",
    "target_muscles": [
      "Psoas major",
      "Sternocleidomastoid"
    ]
  },
  {
    "id": "Lateral Neck Flexion__Neck__Lever (plate loaded)__Sternocleidomastoid",
    "timestamp": "2025-12-10T15:23:05",
    "body_part": "Neck",
    "target_muscles": [
      "Rhomboids"
    ]
  },
  {
    "id": "Neck Flexion__Neck__Weighted__Sternocleidomastoid",
    "timestamp": "2025-11-30T13:12:59",
    "body_part": "Neck",
    "target_muscles": [
      "Psoas major"
    ]
  },
  {
    "id": "Neck Flexion__Neck__Lever (plate loaded)__Sternocleidomastoid",
    "timestamp": "2025-12-07T23:02:53",
    "body_part": "Neck",
    "target_muscles": [
      "Splenius",
      "Sternocleidomastoid"
    ]
  },
  {
    "id": "Neck Retraction__Neck__Band Resistive__Splenius",
    "timestamp": "2025-12-05T21:51:11",
    "body_part": "Neck",
    "target_muscles": [
      "Gluteus Medius"
    ]
  },
  {
    "id": "Lateral Neck Flexion__Neck__Suspended__Sternocleidomastoid",
    "timestamp": "2025-12-02T12:53:28",
    "body_part": "Neck",
    "target_muscles": [
      "Trapezius, Upper"
    ]
  },
  {
    "id": "Neck Flexion__Neck__Suspended__Sternocleidomastoid",
    "timestamp": "2025-12-03T17:07:06",
    "body_part": "Neck",
    "target_muscles": [
      "Rhomboids",
      "Gluteus Medius"
    ]
  },
  {
    "id": "Neck Extension__Neck__Lever (selectorized)__Splenius",
    "timestamp": "2025-12-12T03:23:45",
    "body_part": "Neck",
    "target_muscles": [
      "Psoas major"
    ]
  },
  {
    "id": "Wall Side Neck Bridge__Neck__Body Weight__Sternocleidomastoid",
    "timestamp": "2025-12-01T02:25:04",
    "body_part": "Neck",
    "target_muscles": [
      "Gluteus Medius",
      "Trapezius, Upper"
    ]
  },
  {
    "id": "Neck Flexion__Neck__Cable__Sternocleidomastoid",
    "timestamp": "2025-12-09T18:27:13",
    "body_part": "Neck",
    "target_muscles": [
      "Sternocleidomastoid"
    ]
  },
  {
    "id": "Lateral Neck Flexion__Neck__Weighted__Sternocleidomastoid",
    "timestamp": "2025-12-12T14:40:29",
    "body_part": "Neck",
    "target_muscles": [
      "Splenius",
      "Rhomboids"
    ]
  },
  {
    "id": "Wall Front Neck Bridge__Neck__Body Weight__Sternocleidomastoid",
    "timestamp": "2025-12-08T16:35:59",
    "body_part": "Neck",
    "target_muscles": [
      "Splenius",
      "Psoas major"
    ]
  },
  {
    "id": "Harness__Neck__Weighted__Splenius",
    "timestamp": "2025-12-12T03:40:03",
    "body_part": "Neck",
    "target_muscles": [
      "Trapezius, Upper",
      "Rhomboids"
    ]
  },
  {
    "id": "Lateral Neck Flexion__Neck__Lever (selectorized)__Sternocleidomastoid",
    "timestamp": "2025-12-08T22:50:06",
    "body_part": "Neck",
    "target_muscles": [
      "Trapezius, Upper"
    ]
  },
  {
    "id": "Neck Flexion__Neck__Lever (selectorized)__Sternocleidomastoid",
    "timestamp": "2025-12-13T10:46:57",
    "body_part": "Neck",
    "target_muscles": [
      "Rhomboids",
      "Sternocleidomastoid"
    ]
  },
  {
    "id": "Neck Extension__Neck__Cable__Splenius",
    "timestamp": "2025-12-08T05:48:43",
    "body_part": "Neck",
    "target_muscles": [
      "Psoas major"
    ]
  },
  {
    "id": "Harness__Neck____Splenius",
    "timestamp": "2025-12-12T10:00:08",
    "body_part": "Neck",
    "target_muscles": [
      "Gluteus Medius",
      "Obliques"
    ]
  },
  {
    "id": "Seated Neck Extension__Neck__Weighted__Splenius",
    "timestamp": "2025-12-09T21:47:45",
    "body_part": "Neck",
    "target_muscles": [
      "Trapezius, Upper",
      "Psoas major"
    ]
  },
  {
    "id": "Neck Extension__Neck__Lever (plate loaded)__Splenius",
    "timestamp": "2025-12-02T06:59:40",
    "body_part": "Neck",
    "target_muscles": [
      "Rhomboids",
      "Obliques"
    ]
  }
]
}

kg = ExerciseKGQuery(URI, AUTH)

results = recommend_exercises(user_profile, kg, top_k=5)

for r in results:
    print("=" * 40)
    print("ID:", r["id"])
    print("Name:", r["name"])
    print("Instructions:", r["instructions"][:120], "...")
    print("Target Muscles:", r["target_muscles"])
    
kg.close()
