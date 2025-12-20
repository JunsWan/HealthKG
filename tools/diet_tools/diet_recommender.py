# code/tools/diet_tools/diet_recommender.py

from typing import Dict, Any, List
from tools.diet_tools.query import DietKGQuery
from tools.diet_tools.diet_evaluator import recommend_meals


_NEO4J_URI = "neo4j+ssc://88f8ccae.databases.neo4j.io"
_NEO4J_AUTH = ("neo4j", "_BAD-vDc9fZjk17xTHjAUWaNPoxGxhh1X9oz2-fDffM")

_kg = None


def diet_recommendation_tool(args: Dict[str, Any]) -> List[Dict[str, Any]]:
    global _kg
    if _kg is None:
        _kg = DietKGQuery(_NEO4J_URI, _NEO4J_AUTH)

    results = recommend_meals(args, _kg)

    return results
