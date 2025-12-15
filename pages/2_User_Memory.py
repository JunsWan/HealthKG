# pages/2_User_Memory.py
# -*- coding: utf-8 -*-
import json
import time
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from core.json_utils import dumps
from memory.graph_store import new_graph, apply_patch, keyword_search, summarize


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


def _df_events(events: List[Dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([{
        "type": ev.get("type"),
        "props": json.dumps(ev.get("props", {}), ensure_ascii=False),
        "ts": ev.get("ts", "")
    } for ev in events])


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


def _append_event(g: Dict[str, Any], ev_type: str, props: Dict[str, Any]) -> Dict[str, Any]:
    g["events"].append({"type": ev_type, "props": props, "ts": int(time.time())})
    return g


def main():
    st.title("用户记忆图谱（User Memory Graph）")

    if "user_memory_graph" not in st.session_state:
        st.session_state.user_memory_graph = new_graph()
    st.session_state.user_memory_graph = _ensure_graph(st.session_state.user_memory_graph)

    g = st.session_state.user_memory_graph

    # ===== Top actions =====
    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
    with c1:
        up = st.file_uploader("导入用户记忆图谱 JSON", type=["json"])
        if up is not None:
            try:
                st.session_state.user_memory_graph = _read_uploaded_json(up)
                st.success("已导入")
                st.rerun()
            except Exception as e:
                st.error(f"导入失败：{e}")

    with c2:
        st.download_button(
            "导出用户记忆图谱 JSON",
            data=dumps(g).encode("utf-8"),
            file_name="user_memory_graph.json",
            mime="application/json"
        )

    with c3:
        if st.button("重置图谱", type="secondary"):
            st.session_state.user_memory_graph = new_graph()
            st.warning("已重置")
            st.rerun()

    with c4:
        st.caption("建议：events 很快会膨胀，后续可做“周摘要节点/窗口化保留”。")

    st.divider()

    # ===== Overview =====
    oc1, oc2, oc3 = st.columns(3)
    oc1.metric("nodes", len(g["nodes"]))
    oc2.metric("edges", len(g["edges"]))
    oc3.metric("events", len(g["events"]))

    with st.expander("记忆摘要（给 Router/检索用）", expanded=False):
        st.code(dumps(summarize(g)), language="json")

    # ===== Search =====
    st.subheader("搜索")
    q = st.text_input("关键词搜索（匹配 id/type/props/from/to）", value="")
    if q.strip():
        hits = keyword_search(g, q.strip(), topk=50)
        if hits:
            st.dataframe(pd.DataFrame(hits), use_container_width=True, hide_index=True)
        else:
            st.info("无命中")

    st.divider()

    # ===== Nodes CRUD =====
    st.subheader("节点管理")
    tab_add, tab_edit, tab_del = st.tabs(["新增/覆盖", "编辑", "删除"])

    with tab_add:
        nid = st.text_input("node.id", key="mem_add_nid")
        ntype = st.text_input("node.type", value="User", key="mem_add_ntype")
        props_text = st.text_area("node.props (JSON)", value='{"name": ""}', height=120, key="mem_add_props")
        if st.button("写入节点（upsert）", key="mem_add_btn"):
            try:
                props = json.loads(props_text)
                st.session_state.user_memory_graph = _upsert_node(g, nid, ntype, props)
                st.success("已写入")
                st.rerun()
            except Exception as e:
                st.error(f"失败：{e}")

    with tab_edit:
        node_ids = [n.get("id") for n in g["nodes"] if n.get("id")]
        if not node_ids:
            st.info("暂无节点")
        else:
            sel = st.selectbox("选择节点 id", options=node_ids, key="mem_edit_sel")
            node = next((n for n in g["nodes"] if n.get("id") == sel), None)
            if node:
                ntype2 = st.text_input("node.type", value=node.get("type", ""), key="mem_edit_type")
                props2 = st.text_area("node.props (JSON)", value=json.dumps(node.get("props", {}), ensure_ascii=False, indent=2),
                                      height=140, key="mem_edit_props")
                if st.button("保存修改", key="mem_edit_btn"):
                    try:
                        props_obj = json.loads(props2)
                        st.session_state.user_memory_graph = _upsert_node(g, sel, ntype2, props_obj)
                        st.success("已更新")
                        st.rerun()
                    except Exception as e:
                        st.error(f"失败：{e}")

    with tab_del:
        did = st.text_input("node.id to delete", key="mem_del_nid")
        cascade = st.checkbox("删除关联边（cascade）", value=True, key="mem_del_cascade")
        if st.button("删除节点", key="mem_del_btn"):
            st.session_state.user_memory_graph = _delete_node(g, did, cascade_edges=cascade)
            st.success("已删除")
            st.rerun()

    st.divider()

    # ===== Edges CRUD =====
    st.subheader("边管理")
    tab_eadd, tab_eedit, tab_edel = st.tabs(["新增/覆盖", "编辑", "删除"])

    with tab_eadd:
        eid = st.text_input("edge.id", key="mem_eadd_eid")
        etype = st.text_input("edge.type", value="REL", key="mem_eadd_type")
        efrom = st.text_input("edge.from", key="mem_eadd_from")
        eto = st.text_input("edge.to", key="mem_eadd_to")
        eprops = st.text_area("edge.props (JSON)", value="{}", height=100, key="mem_eadd_props")
        if st.button("写入边（upsert）", key="mem_eadd_btn"):
            try:
                props = json.loads(eprops)
                st.session_state.user_memory_graph = _upsert_edge(g, eid, etype, efrom, eto, props)
                st.success("已写入")
                st.rerun()
            except Exception as e:
                st.error(f"失败：{e}")

    with tab_eedit:
        edge_ids = [e.get("id") for e in g["edges"] if e.get("id")]
        if not edge_ids:
            st.info("暂无边")
        else:
            sel = st.selectbox("选择边 id", options=edge_ids, key="mem_eedit_sel")
            edge = next((e for e in g["edges"] if e.get("id") == sel), None)
            if edge:
                etype2 = st.text_input("edge.type", value=edge.get("type", ""), key="mem_eedit_type")
                efrom2 = st.text_input("edge.from", value=edge.get("from", ""), key="mem_eedit_from")
                eto2 = st.text_input("edge.to", value=edge.get("to", ""), key="mem_eedit_to")
                eprops2 = st.text_area("edge.props (JSON)", value=json.dumps(edge.get("props", {}), ensure_ascii=False, indent=2),
                                       height=120, key="mem_eedit_props")
                if st.button("保存修改", key="mem_eedit_btn"):
                    try:
                        props_obj = json.loads(eprops2)
                        st.session_state.user_memory_graph = _upsert_edge(g, sel, etype2, efrom2, eto2, props_obj)
                        st.success("已更新")
                        st.rerun()
                    except Exception as e:
                        st.error(f"失败：{e}")

    with tab_edel:
        deid = st.text_input("edge.id to delete", key="mem_edel_eid")
        if st.button("删除边", key="mem_edel_btn"):
            st.session_state.user_memory_graph = _delete_edge(g, deid)
            st.success("已删除")
            st.rerun()

    st.divider()

    # ===== Events =====
    st.subheader("事件（events）")
    ev_type = st.text_input("event.type", value="Note", key="mem_ev_type")
    ev_props = st.text_area("event.props (JSON)", value='{"summary": ""}', height=100, key="mem_ev_props")
    if st.button("追加事件", key="mem_ev_btn"):
        try:
            props = json.loads(ev_props)
            st.session_state.user_memory_graph = _append_event(g, ev_type, props)
            st.success("已追加")
            st.rerun()
        except Exception as e:
            st.error(f"失败：{e}")

    with st.expander("Events 表格（最近 200 条）", expanded=False):
        if g["events"]:
            st.dataframe(_df_events(g["events"][-200:]), use_container_width=True, hide_index=True)
        else:
            st.info("暂无事件")

    st.divider()

    # ===== Patch apply (optional) =====
    st.subheader("Patch（可选：手动应用 MemoryUpdater 输出）")
    patch_text = st.text_area("粘贴 patch ops（JSON array）", value="[]", height=120, key="mem_patch_text")
    if st.button("应用 patch 到用户记忆图谱", key="mem_patch_apply"):
        try:
            patch_ops = json.loads(patch_text)
            if not isinstance(patch_ops, list):
                raise ValueError("patch 必须是 JSON array")
            st.session_state.user_memory_graph = apply_patch(g, patch_ops)
            st.success("已应用")
            st.rerun()
        except Exception as e:
            st.error(f"失败：{e}")

    st.divider()

    # ===== Raw tables =====
    st.subheader("原始数据表")
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


if __name__ == "__main__":
    main()