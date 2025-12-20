# code/tools/exercise_recommender.py

from typing import Dict, Any, List, Optional
from threading import Lock

from exercise_tools.query import ExerciseKGQuery
from exercise_tools.recommender_exrx import recommend_exercises


# ============================================================
# Neo4j Client (Exercise)
# ============================================================

_NEO4J_URI = "neo4j+s://7222f7ba.databases.neo4j.io"
_NEO4J_AUTH = ("neo4j", "flF6YWcBHUAR3GFOvDHyo4-ZbpU-NrLhqccto15uoBU")

_kg_client: Optional[ExerciseKGQuery] = None
_kg_lock = Lock()


def _get_kg_client() -> ExerciseKGQuery:
    """
    Lazy-loaded singleton for Neo4j KG client
    """
    global _kg_client
    if _kg_client is None:
        with _kg_lock:
            if _kg_client is None:
                _kg_client = ExerciseKGQuery(_NEO4J_URI, _NEO4J_AUTH)
    return _kg_client


# ============================================================
# MAS Tool Interface
# ============================================================

def recommend_exercise_tool(
    args: Dict[str, Any]
) -> List[Dict[str, Any]]:
    f"""
    MAS Tool: Exercise Recommendation

    Expected args (from Agent / subflow):
    {
        "target_body_part": str,
        "injury_body_part": List[str],
        "available_equipment": List[str],
        "history": List[dict],
        "topk": int (optional)
    }

    history args:
    {
        "id": str,
        "timestamp" : "2025-12-08T21:48:31",
        "body_part" : str,
        "target_muscles" : List[str]
    }
    Returns:
    List[MAS Evidence Dict]
    """

    if not args:
        return []

    target_body_part = args.get("target_body_part")
    injury_body_part = args.get("injury_body_part",[])
    available_equipment = args.get("available_equipment", [])
    history = args.get("history", [])
    topk = int(args.get("topk", 5))

    # 必要字段检查（避免 Neo4j 报错）
    if not target_body_part or not available_equipment:
        return []

    user_profile = {
        "target_body_part": target_body_part,
        "injury_body_part": injury_body_part,
        "available_equipment": available_equipment,
        "history": history,
    }


    try:
        kg = _get_kg_client()
        results = recommend_exercises(
            user_profile=user_profile,
            kg_query=kg,
            top_k=topk
        )
    except Exception as e:
        # MAS 里不能直接抛异常
        print(f"[ExerciseRecommender] Failed: {e}")
        return []

    if not results:
        return []

    # --------------------------------------------------------
    # 3️⃣ Adapt to MAS evidence schema
    # --------------------------------------------------------
    evidences: List[Dict[str, Any]] = []

    for r in results:
        evidence = {
            "id": r.get("id"),
            "name": r.get("name"),
            "summary": r.get("instructions", ""),
            "fields": {
                "target_body_part": target_body_part,
                "utility": r.get("utility"),
                "force": r.get("force"),
                "target muscles": r.get["target_muscles"]
            },
            "source": "Exercise_Recommender"
        }
        evidences.append(evidence)

    '''
    summary : 该动作的详细教程 
    '''

    return evidences


# ============================================================
# Utils
# ============================================================

def _truncate_text(text: Any, max_len: int = 120) -> str:
    """
    Safe text truncation (防止 None / 非字符串)
    """
    if not text:
        return ""
    s = str(text).strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."
