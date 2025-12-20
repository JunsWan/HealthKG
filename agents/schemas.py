# agents/schemas.py
# -*- coding: utf-8 -*-

"""All JSON-returning agents should be called with `response_format`.
- Prefer json_schema (strict) to eliminate fragile `json.loads` parsing failures.
- Keep JSON_OBJECT as a fallback for models/endpoints that don't support json_schema.
"""

# Fallback (JSON mode). Guarantees valid JSON, not full schema compliance.
JSON_OBJECT = {"type": "json_object"}


ROUTER_RESPONSE_FORMAT = {
  "type": "json_schema",
  "json_schema": {
    "name": "router",
    "strict": True,  # Router 结构简单且固定，可以保留 Strict
    "schema": {
      "type": "object",
      "additionalProperties": False,
      "properties": {
        "route": {"type": "string", "enum": [
          "faq_exercise", "faq_food", "query_memory",
          "plan_workout", "plan_diet", "plan_both", "log_update", "other"
        ]},
        "need_clarify": {"type": "boolean"},
        "clarify_questions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "notes": {"type": "string"}
      },
      "required": ["route", "need_clarify", "clarify_questions", "confidence", "notes"]
    }
  }
}


INTENT_PARSER_RESPONSE_FORMAT = {
  "type": "json_schema",
  "json_schema": {
    "name": "intent_parser",
    "strict": True, # IntentParser 定义完整，无通用 Object，保留 Strict
    "schema": {
      "type": "object",
      "additionalProperties": False,
      "properties": {
        "task_type": {"type": "string", "enum": [
          "训练规划", "饮食规划", "训练+饮食", "记录/复盘", "问答科普", "其他"
        ]},
        "goals": {
          "type": "object",
          "additionalProperties": False,
          "properties": {
            "primary": {"type": "string"},
            "secondary": {"type": "string"}
          },
          "required": ["primary", "secondary"]
        },
        "constraints": {
          "type": "object",
          "additionalProperties": False,
          "properties": {
            "time_min": {"type": "number"},
            "days_per_week": {"type": "number"},
            "equipment": {"type": "array", "items": {"type": "string"}},
            "injury": {"type": "array", "items": {"type": "string"}},
            "schedule_pref": {"type": "string"}
          },
          "required": ["time_min", "days_per_week", "equipment", "injury", "schedule_pref"]
        },
        "preferences": {
          "type": "object",
          "additionalProperties": False,
          "properties": {
            "diet": {"type": "array", "items": {"type": "string"}},
            "training": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["diet", "training"]
        },
        "entities": {
          "type": "object",
          "additionalProperties": False,
          "properties": {
            "muscle_groups": {"type": "array", "items": {"type": "string"}},
            "exercises": {"type": "array", "items": {"type": "string"}},
            "foods": {"type": "array", "items": {"type": "string"}},
            "metrics": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["muscle_groups", "exercises", "foods", "metrics"]
        },
        "missing_slots": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"}
      },
      "required": [
        "task_type", "goals", "constraints", "preferences", "entities", "missing_slots", "confidence"
      ]
    }
  }
}


MEMORY_RETRIEVER_RESPONSE_FORMAT = {
  "type": "json_schema",
  "json_schema": {
    "name": "memory_retriever",
    "strict": False, # [FIX] 包含 baseline (generic object)，必须关闭 strict
    "schema": {
      "type": "object",
      "properties": {
        "profile_summary": {
          "type": "object",
          "properties": {
            "level": {"type": "string"},
            "goal": {"type": "string"},
            "baseline": {"type": "object"} # Dynamic dict
          },
          "required": ["level", "goal", "baseline"]
        },
        "recent_events": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "event_ref": {"type": "string"},
              "type": {"type": "string"},
              "summary": {"type": "string"}
            },
            "required": ["event_ref", "type", "summary"]
          }
        },
        "hard_constraints": {
          "type": "object",
          "properties": {
            "injury": {"type": "array", "items": {"type": "string"}},
            "time": {
              "type": "object",
              "properties": {
                "time_min": {"type": "number"},
                "days_per_week": {"type": "number"}
              },
              "required": ["time_min", "days_per_week"]
            },
            "equipment": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["injury", "time", "equipment"]
        },
        "soft_preferences": {
          "type": "object",
          "properties": {
            "foods": {"type": "array", "items": {"type": "string"}},
            "training_style": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["foods", "training_style"]
        },
        "facts": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "key": {"type": "string"},
              "value": {"type": "string"},
              "ref": {"type": "string"}
            },
            "required": ["key", "value", "ref"]
          }
        },
        "evidence": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"]
          }
        }
      },
      "required": ["profile_summary", "recent_events", "hard_constraints", "soft_preferences", "facts", "evidence"]
    }
  }
}


PLAN_DRAFT_RESPONSE_FORMAT = {
  "type": "json_schema",
  "json_schema": {
    "name": "plan_draft",
    "strict": False, # [FIX] 包含 args 和 template items (generic)，必须关闭 strict
    "schema": {
      "type": "object",
      "properties": {
        "workout_draft": {
          "type": "object",
          "properties": {
            "split": {"type": "string"},
            "sessions": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "name": {"type": "string"},
                  "duration_min": {"type": "number"},
                  "items": {
                    "type": "array",
                    "items": {
                      "type": "object",
                      "properties": {
                        "exercise": {"type": "string"},
                        "sets": {"type": "number"},
                        "reps": {"type": "string"},
                        "intensity": {"type": "string"},
                        "rest_sec": {"type": "number"},
                        "notes": {"type": "array", "items": {"type": "string"}}
                      },
                      "required": ["exercise", "sets", "reps", "intensity", "rest_sec", "notes"]
                    }
                  },
                  "notes": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["name", "duration_min", "items", "notes"]
              }
            },
            "notes": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["split", "sessions", "notes"]
        },
        "diet_draft": {
          "type": "object",
          "properties": {
            "macro_target": {
              "type": "object",
              "properties": {
                "kcal": {"type": "number"},
                "protein_g": {"type": "number"},
                "carb_g": {"type": "number"},
                "fat_g": {"type": "number"}
              },
              "required": ["kcal", "protein_g", "carb_g", "fat_g"]
            },
            "meals": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "name": {"type": "string"},
                  "template": {"type": "array", "items": {}}, # Dynamic
                  "fallbacks": {"type": "array", "items": {}}, # Dynamic
                  "notes": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["name", "template", "fallbacks", "notes"]
              }
            },
            "notes": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["macro_target", "meals", "notes"]
        },
        "kg_queries": {
          "type": "object",
          "properties": {
            "exercise": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "tool": {"type": "string"},
                  "args": {"type": "object"} # Dynamic
                },
                "required": ["tool", "args"]
              }
            },
            "nutrition": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "tool": {"type": "string"},
                  "args": {"type": "object"} # Dynamic
                },
                "required": ["tool", "args"]
              }
            }
          },
          "required": ["exercise", "nutrition"]
        },
        "draft_refs": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "draft_ref": {"type": "string"},
              "what": {"type": "string"}
            },
            "required": ["draft_ref", "what"]
          }
        }
      },
      "required": ["workout_draft", "diet_draft", "kg_queries", "draft_refs"]
    }
  }
}


KNOWLEDGE_RETRIEVER_RESPONSE_FORMAT = {
  "type": "json_schema",
  "json_schema": {
    "name": "knowledge_retriever",
    "strict": False, # [FIX] 包含 args 和 fields (generic)，必须关闭 strict
    "schema": {
      "type": "object",
      "properties": {
        "tool_calls": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "tool": {"type": "string", "enum": ["retrieve_exercise_kg", "retrieve_nutrition_kg"]},
              "args": {
                "type": "object",
                "properties": {
                  # 针对 exercise 必须产生这三个参数
                  "target_body_part": {"type": "string", "description": "Target muscle or body part (e.g., Chest, Back, Legs)"},
                  "injury_body_part": {"type": "string", "description": "Body part to avoid due to injury"},
                  "available_equipment": {"type": "array", "items": {"type": "string"}},
                  # 兼容 nutrition 依然用 query
                  "query": {"type": "string"} 
                },
                # 这里不要 strict required，因为不同工具需要的参数不一样，靠 Agent 自己判断
              }
            },
            "required": ["tool", "args"]
          }
        },
        "evidence_cards": {
          "type": "object",
          "properties": {
            "exercise_kg": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "evidence_id": {"type": "string"},
                  "name": {"type": "string"},
                  "summary": {"type": "string"},
                  "fields": {"type": "object"}, # Dynamic
                  "source": {"type": "string"}
                },
                "required": ["evidence_id", "name", "summary", "fields", "source"]
              }
            },
            "nutrition_kg": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "evidence_id": {"type": "string"},
                  "name": {"type": "string"},
                  "summary": {"type": "string"},
                  "fields": {"type": "object"}, # Dynamic
                  "source": {"type": "string"}
                },
                "required": ["evidence_id", "name", "summary", "fields", "source"]
              }
            }
          },
          "required": ["exercise_kg", "nutrition_kg"]
        },
        "support_map": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "draft_ref": {"type": "string"},
              "evidence_id": {"type": "string"}
            },
            "required": ["draft_ref", "evidence_id"]
          }
        }
      },
      "required": ["tool_calls", "evidence_cards", "support_map"]
    }
  }
}


REASONER_RESPONSE_FORMAT = {
  "type": "json_schema",
  "json_schema": {
    "name": "reasoner",
    "strict": False, # [FIX] 包含 generic items，建议关闭 strict 以防万一
    "schema": {
      "type": "object",
      "properties": {
        "final_plan": {
          "type": "object",
          "properties": {
            "workout": {
              "type": "object",
              "properties": {
                "schedule": {"type": "string"},
                "sessions": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "name": {"type": "string"},
                      "duration_min": {"type": "number"},
                      "items": {
                        "type": "array",
                        "items": {
                          "type": "object",
                          "properties": {
                            "exercise": {"type": "string"},
                            "sets": {"type": "number"},
                            "reps": {"type": "string"},
                            "intensity": {"type": "string"},
                            "rest_sec": {"type": "number"},
                            "notes": {"type": "array", "items": {"type": "string"}}
                          },
                          "required": ["exercise", "sets", "reps", "intensity", "rest_sec", "notes"]
                        }
                      },
                      "notes": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["name", "duration_min", "items", "notes"]
                  }
                },
                "notes": {"type": "array", "items": {"type": "string"}}
              },
              "required": ["schedule", "sessions", "notes"]
            },
            "diet": {
              "type": "object",
              "properties": {
                "macro_target": {
                  "type": "object",
                  "properties": {
                    "kcal": {"type": "number"},
                    "protein_g": {"type": "number"},
                    "carb_g": {"type": "number"},
                    "fat_g": {"type": "number"}
                  },
                  "required": ["kcal", "protein_g", "carb_g", "fat_g"]
                },
                "meal_templates": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "name": {"type": "string"},
                      "items": {"type": "array", "items": {}}, # Dynamic
                      "notes": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["name", "items", "notes"]
                  }
                },
                "notes": {"type": "array", "items": {"type": "string"}}
              },
              "required": ["macro_target", "meal_templates", "notes"]
            }
          },
          "required": ["workout", "diet"]
        },
        "change_log": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "where": {"type": "string"},
              "from": {"type": "string"},
              "to": {"type": "string"},
              "why": {"type": "string"}
            },
            "required": ["where", "from", "to", "why"]
          }
        },
        "rationale": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "type": {"type": "string"},
              "ref": {"type": "string"}
            },
            "required": ["type", "ref"]
          }
        },
        "risks": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "risk": {"type": "string"},
              "severity": {"type": "string", "enum": ["low", "mid", "high"]},
              "mitigation": {"type": "string"}
            },
            "required": ["risk", "severity", "mitigation"]
          }
        },
        "confidence": {"type": "number"}
      },
      "required": ["final_plan", "change_log", "rationale", "risks", "confidence"]
    }
  }
}


MEMORY_UPDATER_RESPONSE_FORMAT = {
  "type": "json_schema",
  "json_schema": {
    "name": "memory_updater_patch_ops",
    "strict": False, # [FIX] props 是动态 dict，必须关闭 strict
    "schema": {
      "type": "object",
      "properties": {
        "ops": {
          "type": "array",
          "items": {
            "oneOf": [
              {
                "type": "object",
                "properties": {
                  "op": {"type": "string", "const": "append_event"},
                  "event": {
                    "type": "object",
                    "properties": {
                      "type": {"type": "string", "enum": [
                        "Plan", "WorkoutLog", "DietLog", "Metric", "SymptomEvent", "QA", "Note"
                      ]},
                      "props": {"type": "object"}
                    },
                    "required": ["type", "props"]
                  }
                },
                "required": ["op", "event"]
              },
              {
                "type": "object",
                "properties": {
                  "op": {"type": "string", "const": "add_node"},
                  "id": {"type": "string"},
                  "type": {"type": "string"},
                  "props": {"type": "object"}
                },
                "required": ["op", "id", "type", "props"]
              },
              {
                "type": "object",
                "properties": {
                  "op": {"type": "string", "const": "add_edge"},
                  "id": {"type": "string"},
                  "type": {"type": "string"},
                  "from": {"type": "string"},
                  "to": {"type": "string"},
                  "props": {"type": "object"}
                },
                "required": ["op", "id", "type", "from", "to", "props"]
              },
              {
                "type": "object",
                "properties": {
                  "op": {"type": "string", "const": "update_node"},
                  "id": {"type": "string"},
                  "props": {"type": "object"}
                },
                "required": ["op", "id", "props"]
              }
            ]
          }
        }
      },
      "required": ["ops"]
    }
  }
}