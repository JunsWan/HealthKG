# pages/3_KG_Manager.py
# -*- coding: utf-8 -*-
import json
import time
import os
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from core.json_utils import dumps
from memory.graph_store import new_graph
from memory.persistence import save_graph, load_graph
from tools.kg_retrieval import retrieve_exercise_kg, retrieve_nutrition_kg

DATA_DIR = os.getenv("DATA_DIR", "./data")
PATH_EXERCISE = os.path.join(DATA_DIR, "exercise_kg.json")
PATH_NUTRITION = os.path.join(DATA_DIR, "nutrition_kg.json")

def _kg_path(ss_key: str) -> str:
    if ss_key == "exercise_kg":
        return PATH_EXERCISE
    if ss_key == "nutrition_kg":
        return PATH_NUTRITION
    return os.path.join(DATA_DIR, f"{ss_key}.json")

def _dirty_key(ss_key: str) -> str:
    return f"{ss_key}__dirty"


def _ensure_graph(g: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(g, dict):
        g = {}
    g.setdefault("nodes", [])
    g.setdefault("edges", [])
    g.setdefault("events", [])
    return g


def _read_uploaded_json(upload) -> Dict[str, Any]:
    data = json.loads(upload.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON 顶层必须是 object（dict）")
    return _ensure_graph(data)


def _df_nodes(nodes: List[Dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([{
        "id": n.get("id"),
        "type": n.get("type"),
        "props": json.dumps(n.get("props", {}), ensure_ascii=False),
        "last_updated": n.get("last_updated", "")
    } for n in nodes])


def _df_edges(edges: List[Dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([{
        "id": e.get("id"),
        "type": e.get("type"),
        "from": e.get("from"),
        "to": e.get("to"),
        "props": json.dumps(e.get("props", {}), ensure_ascii=False),
        "last_updated": e.get("last_updated", "")
    } for e in edges])


def _upsert_node(g: Dict[str, Any], node_id: str, node_type: str, props: Dict[str, Any]) -> Dict[str, Any]:
    now = int(time.time())
    for n in g["nodes"]:
        if n.get("id") == node_id:
            n["type"] = node_type
            n["props"] = props
            n["last_updated"] = now
            return g
    g["nodes"].append({"id": node_id, "type": node_type, "props": props, "last_updated": now})
    return g


def _delete_node(g: Dict[str, Any], node_id: str, cascade_edges: bool = True) -> Dict[str, Any]:
    g["nodes"] = [n for n in g["nodes"] if n.get("id") != node_id]
    if cascade_edges:
        g["edges"] = [e for e in g["edges"] if e.get("from") != node_id and e.get("to") != node_id]
    return g


def _upsert_edge(g: Dict[str, Any], edge_id: str, edge_type: str, efrom: str, eto: str, props: Dict[str, Any]) -> Dict[str, Any]:
    now = int(time.time())
    for e in g["edges"]:
        if e.get("id") == edge_id:
            e["type"] = edge_type
            e["from"] = efrom
            e["to"] = eto
            e["props"] = props
            e["last_updated"] = now
            return g
    g["edges"].append({"id": edge_id, "type": edge_type, "from": efrom, "to": eto, "props": props, "last_updated": now})
    return g


def _delete_edge(g: Dict[str, Any], edge_id: str) -> Dict[str, Any]:
    g["edges"] = [e for e in g["edges"] if e.get("id") != edge_id]
    return g


def kg_panel(
    ss_key: str,
    title: str,
    retrieve_fn_name: str,
):
    st.subheader(title)

    path = _kg_path(ss_key)
    if _dirty_key(ss_key) not in st.session_state:
        st.session_state[_dirty_key(ss_key)] = False

    sc1, sc2, sc3 = st.columns([3, 2, 3])
    with sc1:
        if st.session_state[_dirty_key(ss_key)]:
            st.warning("当前 KG 有未保存的更改")
        else:
            st.info("当前 KG 已保存")
    with sc2:
        if st.button("保存到磁盘", key=f"save_btn_{ss_key}"):
            try:
                save_graph(path, st.session_state[ss_key])
                st.session_state[_dirty_key(ss_key)] = False
                st.success(f"已保存到 {path}")
            except Exception as e:
                st.error(f"保存失败：{e}")
    with sc3:
        st.caption("说明：只有点击“保存到磁盘”才会写入文件；否则修改仅在本次会话内生效。")

    if ss_key not in st.session_state:
        st.session_state[ss_key] = load_graph(path, new_graph())
    st.session_state[ss_key] = _ensure_graph(st.session_state[ss_key])
    g = st.session_state[ss_key]

    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        up = st.file_uploader(f"导入 {title} JSON", type=["json"], key=f"upload_{ss_key}")
        if up is not None:
            try:
                st.session_state[ss_key] = _read_uploaded_json(up)
                st.session_state[_dirty_key(ss_key)] = True
                st.success("已导入")
                st.rerun()
            except Exception as e:
                st.error(f"导入失败：{e}")

    with c2:
        st.download_button(
            f"导出 {title} JSON",
            data=dumps(g).encode("utf-8"),
            file_name=f"{ss_key}.json",
            mime="application/json"
        )

    with c3:
        if st.button("清空 KG", key=f"clear_{ss_key}"):
            st.session_state[ss_key] = new_graph()
            st.session_state[_dirty_key(ss_key)] = True
            st.warning("已清空")
            st.rerun()

    st.caption("提示：领域 KG 通常不需要 events；你可以只维护 nodes/edges。")

    st.divider()

    oc1, oc2 = st.columns(2)
    oc1.metric("nodes", len(g["nodes"]))
    oc2.metric("edges", len(g["edges"]))

    # ===== Quick retrieval demo =====
    st.markdown("### 检索 Demo（用于展示接口已预留）")
    q = st.text_input("查询（用于检索 evidence）", key=f"demo_q_{ss_key}")
    topk = st.slider("topk", 1, 20, 8, key=f"demo_topk_{ss_key}")
    if st.button("运行检索", key=f"demo_run_{ss_key}"):
        args = {"query": q, "topk": topk}
        if retrieve_fn_name == "exercise":
            evid = retrieve_exercise_kg(args, g)
        else:
            evid = retrieve_nutrition_kg(args, g)
        st.session_state[f"demo_evid_{ss_key}"] = evid

    evid = st.session_state.get(f"demo_evid_{ss_key}", [])
    if evid:
        st.dataframe(pd.DataFrame(evid), use_container_width=True, hide_index=True)
    else:
        st.info("暂无 evidence（导入 KG 或添加节点后再试）")

    st.divider()

    # ===== CRUD =====
    st.markdown("### 节点管理")
    tab_add, tab_edit, tab_del = st.tabs(["新增/覆盖", "编辑", "删除"])

    with tab_add:
        nid = st.text_input("node.id", key=f"add_nid_{ss_key}")
        ntype = st.text_input("node.type", value="entity", key=f"add_ntype_{ss_key}")
        props_text = st.text_area("node.props (JSON)", value='{"name": ""}', height=120, key=f"add_props_{ss_key}")
        if st.button("写入节点（upsert）", key=f"add_btn_{ss_key}"):
            try:
                props = json.loads(props_text)
                st.session_state[ss_key] = _upsert_node(g, nid, ntype, props)
                st.session_state[_dirty_key(ss_key)] = True
                st.success("已写入")
                st.rerun()
            except Exception as e:
                st.error(f"失败：{e}")

    with tab_edit:
        node_ids = [n.get("id") for n in g["nodes"] if n.get("id")]
        if not node_ids:
            st.info("暂无节点")
        else:
            sel = st.selectbox("选择节点 id", options=node_ids, key=f"edit_sel_{ss_key}")
            node = next((n for n in g["nodes"] if n.get("id") == sel), None)
            if node:
                ntype2 = st.text_input("node.type", value=node.get("type", ""), key=f"edit_type_{ss_key}")
                props2 = st.text_area("node.props (JSON)",
                                      value=json.dumps(node.get("props", {}), ensure_ascii=False, indent=2),
                                      height=140, key=f"edit_props_{ss_key}")
                if st.button("保存修改", key=f"edit_btn_{ss_key}"):
                    try:
                        props_obj = json.loads(props2)
                        st.session_state[ss_key] = _upsert_node(g, sel, ntype2, props_obj)
                        st.session_state[_dirty_key(ss_key)] = True
                        st.success("已更新")
                        st.rerun()
                    except Exception as e:
                        st.error(f"失败：{e}")

    with tab_del:
        did = st.text_input("node.id to delete", key=f"del_nid_{ss_key}")
        cascade = st.checkbox("删除关联边（cascade）", value=True, key=f"del_cascade_{ss_key}")
        if st.button("删除节点", key=f"del_btn_{ss_key}"):
            st.session_state[ss_key] = _delete_node(g, did, cascade_edges=cascade)
            st.session_state[_dirty_key(ss_key)] = True
            st.success("已删除")
            st.rerun()

    st.markdown("### 边管理")
    tab_eadd, tab_eedit, tab_edel = st.tabs(["新增/覆盖", "编辑", "删除"])

    with tab_eadd:
        eid = st.text_input("edge.id", key=f"eadd_eid_{ss_key}")
        etype = st.text_input("edge.type", value="REL", key=f"eadd_type_{ss_key}")
        efrom = st.text_input("edge.from", key=f"eadd_from_{ss_key}")
        eto = st.text_input("edge.to", key=f"eadd_to_{ss_key}")
        eprops = st.text_area("edge.props (JSON)", value="{}", height=100, key=f"eadd_props_{ss_key}")
        if st.button("写入边（upsert）", key=f"eadd_btn_{ss_key}"):
            try:
                props = json.loads(eprops)
                st.session_state[ss_key] = _upsert_edge(g, eid, etype, efrom, eto, props)
                st.session_state[_dirty_key(ss_key)] = True
                st.success("已写入")
                st.rerun()
            except Exception as e:
                st.error(f"失败：{e}")

    with tab_eedit:
        edge_ids = [e.get("id") for e in g["edges"] if e.get("id")]
        if not edge_ids:
            st.info("暂无边")
        else:
            sel = st.selectbox("选择边 id", options=edge_ids, key=f"eedit_sel_{ss_key}")
            edge = next((e for e in g["edges"] if e.get("id") == sel), None)
            if edge:
                etype2 = st.text_input("edge.type", value=edge.get("type", ""), key=f"eedit_type_{ss_key}")
                efrom2 = st.text_input("edge.from", value=edge.get("from", ""), key=f"eedit_from_{ss_key}")
                eto2 = st.text_input("edge.to", value=edge.get("to", ""), key=f"eedit_to_{ss_key}")
                eprops2 = st.text_area("edge.props (JSON)",
                                       value=json.dumps(edge.get("props", {}), ensure_ascii=False, indent=2),
                                       height=120, key=f"eedit_props_{ss_key}")
                if st.button("保存修改", key=f"eedit_btn_{ss_key}"):
                    try:
                        props_obj = json.loads(eprops2)
                        st.session_state[ss_key] = _upsert_edge(g, sel, etype2, efrom2, eto2, props_obj)
                        st.session_state[_dirty_key(ss_key)] = True
                        st.success("已更新")
                        st.rerun()
                    except Exception as e:
                        st.error(f"失败：{e}")

    with tab_edel:
        deid = st.text_input("edge.id to delete", key=f"edel_eid_{ss_key}")
        if st.button("删除边", key=f"edel_btn_{ss_key}"):
            st.session_state[ss_key] = _delete_edge(g, deid)
            st.session_state[_dirty_key(ss_key)] = True
            st.success("已删除")
            st.rerun()

    st.divider()

    st.markdown("### 原始数据表")
    with st.expander("Nodes", expanded=False):
        if g["nodes"]:
            st.dataframe(_df_nodes(g["nodes"]), use_container_width=True, hide_index=True)
        else:
            st.info("暂无节点")
    with st.expander("Edges", expanded=False):
        if g["edges"]:
            st.dataframe(_df_edges(g["edges"]), use_container_width=True, hide_index=True)
        else:
            st.info("暂无边")


def main():
    st.title("领域知识图谱管理（KG Manager）")

    if "exercise_kg" not in st.session_state:
        st.session_state.exercise_kg = new_graph()
    if "nutrition_kg" not in st.session_state:
        st.session_state.nutrition_kg = new_graph()

    tab1, tab2 = st.tabs(["健身动作图谱（Exercise KG）", "饮食健康图谱（Nutrition KG）"])

    with tab1:
        kg_panel("exercise_kg", "健身动作图谱", retrieve_fn_name="exercise")

    with tab2:
        kg_panel("nutrition_kg", "饮食健康图谱", retrieve_fn_name="nutrition")


if __name__ == "__main__":
    main()