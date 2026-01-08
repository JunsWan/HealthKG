from neo4j import GraphDatabase
import json
from tqdm import tqdm


# ============================================================
# Neo4j Config
# ============================================================
URI = "your neo4j url"
AUTH = ("neo4j", "password")
INPUT_JSON = "../data/exrx_final.json"


# ============================================================
# Utility: build exercise_id
# ============================================================
def make_exercise_id(item):
    targets = "_".join(item.get("Muscles", {}).get("Target", []))
    return f"{item['exercise_name']}__{item['body_part']}__{item['training_type']}__{targets}"


# ============================================================
# Cypher: core ExerciseVariant
# ============================================================
BASE_QUERY = """
MERGE (ev:ExerciseVariant {id: $exercise_id})
SET ev.name = $exercise_name,
    ev.instructions = $instructions,
    ev.utility = $utility,
    ev.mechanics = $mechanics,
    ev.force = $force,
    ev.comments = $comments

MERGE (tbp:TrainingBodyPart {name: $body_part})
MERGE (ev)-[:TRAINS_BODY_PART]->(tbp)

MERGE (eq:Equipment {name: $training_type})
MERGE (ev)-[:USES_EQUIPMENT]->(eq)
"""


# ============================================================
# Cypher: muscle relations (FIXED)
# ============================================================
MUSCLE_QUERY = """
UNWIND $muscles AS m
MERGE (mu:Muscle {name: m})
WITH mu
MATCH (ev:ExerciseVariant {id: $exercise_id})
MERGE (ev)-[r:REL]->(mu)
"""


# ============================================================
# Cypher: instruction body parts (FIXED)
# ============================================================
INSTRUCTION_BP_QUERY = """
UNWIND $body_parts AS bp
MERGE (ibp:InstructionBodyPart {name: bp})
WITH ibp
MATCH (ev:ExerciseVariant {id: $exercise_id})
MERGE (ev)-[:INVOLVES_BODY_PART]->(ibp)
"""


# ============================================================
# Main loader
# ============================================================
def load_to_neo4j(uri, auth, json_file):
    driver = GraphDatabase.driver(uri, auth=auth)

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    with driver.session() as session:
        for item in tqdm(data, desc="Importing ExerciseVariants"):

            exercise_id = make_exercise_id(item)
            muscles = item.get("Muscles", {})

            # Step 1: core node
            session.run(
                BASE_QUERY,
                exercise_id=exercise_id,
                exercise_name=item["exercise_name"],
                instructions=item.get("Instructions"),
                utility=item.get("Utility"),
                mechanics=item.get("Mechanics"),
                force=item.get("Force"),
                comments=item.get("Comments"),
                body_part=item["body_part"],
                training_type=item["training_type"],
            )

            # Step 2: muscles
            for rel, key in [
                ("TARGETS", "Target"),
                ("SYNERGIZES", "Synergists"),
                ("STABILIZES", "Stabilizers"),
            ]:
                values = muscles.get(key, [])
                if values and values != ["None"]:
                    session.run(
                        MUSCLE_QUERY.replace("REL", rel),
                        exercise_id=exercise_id,
                        muscles=values
                    )

            # Step 3: instruction body parts
            instr_bps = item.get("Instruction_BodyPart", [])
            if instr_bps:
                session.run(
                    INSTRUCTION_BP_QUERY,
                    exercise_id=exercise_id,
                    body_parts=instr_bps
                )

    driver.close()
    print("🎉 ExerciseVariant Knowledge Graph imported successfully!")


# ============================================================
# Entry
# ============================================================
if __name__ == "__main__":
    load_to_neo4j(URI, AUTH, INPUT_JSON)
