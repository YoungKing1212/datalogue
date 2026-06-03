from typing import List
import json
import logging

import yaml
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app import schemas, models
from app.graph.llm import get_llm

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=List[schemas.DatasetOut])
def list_datasets(datasource_id: int | None = None, db: Session = Depends(get_db)):
    logger.info(f"获取数据集列表: datasource_id={datasource_id}")
    q = db.query(models.SemanticDataset)
    if datasource_id:
        q = q.filter(models.SemanticDataset.datasource_id == datasource_id)
    result = q.order_by(models.SemanticDataset.id.desc()).all()
    logger.info(f"返回 {len(result)} 个数据集")
    return result


@router.post("", response_model=schemas.DatasetOut)
def create_dataset(payload: schemas.DatasetCreate, db: Session = Depends(get_db)):
    logger.info(f"创建数据集: name={payload.name}")
    ds = models.SemanticDataset(**payload.model_dump())
    db.add(ds)
    db.commit()
    db.refresh(ds)
    logger.info(f"数据集创建成功: id={ds.id}")
    return ds


@router.get("/{ds_id}", response_model=schemas.DatasetOut)
def get_dataset(ds_id: int, db: Session = Depends(get_db)):
    """获取单个数据集详情。"""
    logger.info(f"获取数据集详情: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    return ds


@router.put("/{ds_id}", response_model=schemas.DatasetOut)
def update_dataset(ds_id: int, payload: schemas.DatasetUpdate, db: Session = Depends(get_db)):
    """部分更新数据集信息（重命名、修改描述/状态等）。"""
    logger.info(f"更新数据集: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(ds, key, value)
    db.commit()
    db.refresh(ds)
    logger.info(f"数据集更新成功: ds_id={ds_id}")
    return ds


@router.delete("/{ds_id}")
def delete_dataset(ds_id: int, db: Session = Depends(get_db)):
    """删除数据集及其关联的指标、维度和已选源表关联。"""
    logger.info(f"删除数据集: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    # 显式级联删除关联记录，避免 ORM 默认 SET NULL 与 NOT NULL 冲突
    db.query(models.SemanticMetric).filter(models.SemanticMetric.dataset_id == ds_id).delete()
    db.query(models.SemanticDimension).filter(models.SemanticDimension.dataset_id == ds_id).delete()
    db.query(models.DatasetSourceTable).filter(
        models.DatasetSourceTable.dataset_id == ds_id
    ).delete()
    db.delete(ds)
    db.commit()
    logger.info(f"数据集删除成功: ds_id={ds_id}")
    return {"ok": True}


# ── Metrics ──────────────────────────────────────────


@router.post("/{ds_id}/metric", response_model=schemas.MetricOut)
def add_metric(ds_id: int, payload: schemas.MetricCreate, db: Session = Depends(get_db)):
    logger.info(f"添加指标: ds_id={ds_id}, name={payload.name}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    m = models.SemanticMetric(dataset_id=ds_id, **payload.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    logger.info(f"指标添加成功: id={m.id}")
    return m


@router.put("/{ds_id}/metric/{mid}", response_model=schemas.MetricOut)
def update_metric(
    ds_id: int, mid: int, payload: schemas.MetricCreate, db: Session = Depends(get_db)
):
    """更新指标。"""
    logger.info(f"更新指标: ds_id={ds_id}, mid={mid}")
    m = db.get(models.SemanticMetric, mid)
    if not m or m.dataset_id != ds_id:
        logger.warning(f"指标不存在: ds_id={ds_id}, mid={mid}")
        raise HTTPException(status_code=404, detail="指标不存在")
    for key, value in payload.model_dump().items():
        setattr(m, key, value)
    db.commit()
    db.refresh(m)
    logger.info(f"指标更新成功: mid={mid}")
    return m


@router.get("/{ds_id}/metrics", response_model=List[schemas.MetricOut])
def list_metrics(ds_id: int, db: Session = Depends(get_db)):
    """获取数据集下的所有指标。"""
    return db.query(models.SemanticMetric).filter(models.SemanticMetric.dataset_id == ds_id).all()


@router.delete("/{ds_id}/metric/{mid}")
def delete_metric(ds_id: int, mid: int, db: Session = Depends(get_db)):
    """删除指标。"""
    logger.info(f"删除指标: ds_id={ds_id}, mid={mid}")
    m = db.get(models.SemanticMetric, mid)
    if not m or m.dataset_id != ds_id:
        logger.warning(f"指标不存在: ds_id={ds_id}, mid={mid}")
        raise HTTPException(status_code=404, detail="指标不存在")
    db.delete(m)
    db.commit()
    logger.info(f"指标删除成功: mid={mid}")
    return {"ok": True}


# ── Dimensions ───────────────────────────────────────


@router.post("/{ds_id}/dimension", response_model=schemas.DimensionOut)
def add_dimension(ds_id: int, payload: schemas.DimensionCreate, db: Session = Depends(get_db)):
    logger.info(f"添加维度: ds_id={ds_id}, name={payload.name}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")
    d = models.SemanticDimension(dataset_id=ds_id, **payload.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    logger.info(f"维度添加成功: id={d.id}")
    return d


@router.put("/{ds_id}/dimension/{did}", response_model=schemas.DimensionOut)
def update_dimension(
    ds_id: int, did: int, payload: schemas.DimensionCreate, db: Session = Depends(get_db)
):
    """更新维度。"""
    logger.info(f"更新维度: ds_id={ds_id}, did={did}")
    d = db.get(models.SemanticDimension, did)
    if not d or d.dataset_id != ds_id:
        logger.warning(f"维度不存在: ds_id={ds_id}, did={did}")
        raise HTTPException(status_code=404, detail="维度不存在")
    for key, value in payload.model_dump().items():
        setattr(d, key, value)
    db.commit()
    db.refresh(d)
    logger.info(f"维度更新成功: did={did}")
    return d


@router.get("/{ds_id}/dimensions", response_model=List[schemas.DimensionOut])
def list_dimensions(ds_id: int, db: Session = Depends(get_db)):
    """获取数据集下的所有维度。"""
    return (
        db.query(models.SemanticDimension)
        .filter(models.SemanticDimension.dataset_id == ds_id)
        .all()
    )


@router.delete("/{ds_id}/dimension/{did}")
def delete_dimension(ds_id: int, did: int, db: Session = Depends(get_db)):
    """删除维度。"""
    logger.info(f"删除维度: ds_id={ds_id}, did={did}")
    d = db.get(models.SemanticDimension, did)
    if not d or d.dataset_id != ds_id:
        logger.warning(f"维度不存在: ds_id={ds_id}, did={did}")
        raise HTTPException(status_code=404, detail="维度不存在")
    db.delete(d)
    db.commit()
    logger.info(f"维度删除成功: did={did}")
    return {"ok": True}


# ── LLM Auto Annotation ──────────────────────────────


@router.post("/{ds_id}/annotate-columns")
def annotate_dataset_columns(ds_id: int, db: Session = Depends(get_db)):
    """调用 LLM 自动标注 **当前数据集已选中的表**（非数据源下全量表）。

    委托给 app.services.annotation.annotate_table_columns（统一服务），
    同时标注 **表级**（ai_description / table_comment 增强）和 **列级**
    （ai_description / ai_semantic_role / ai_suggested_agg），并刷新 effective_desc。
    """
    logger.info(f"自动标注字段: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    # 只标注「当前数据集已选中的表」：避免对数据源下未选中的表烧 token
    selected_links = (
        db.query(models.DatasetSourceTable).filter_by(dataset_id=ds_id).all()
    )
    selected_table_ids = [link.source_table_id for link in selected_links]
    if not selected_table_ids:
        raise HTTPException(status_code=400, detail="该数据集尚未选择任何表，请先在「数据源表」中勾选要纳入数据集的表")

    tables = (
        db.query(models.SourceTable)
        .filter(models.SourceTable.id.in_(selected_table_ids))
        .all()
    )

    # 委托给统一标注服务（同时跑表级 + 列级，写 ai_description / effective_desc）
    from app.services.annotation import annotate_table_columns as svc_annotate

    total_annotated = 0
    total_skipped = 0
    total_table_annotated = 0
    failed_tables: list[dict] = []
    total_metrics = 0
    total_dims = 0
    total_times = 0

    for table in tables:
        try:
            result = svc_annotate(db, table.id, force=False)
        except Exception as e:
            logger.error(f"标注表 {table.table_name} 失败: {e}")
            failed_tables.append({"table": table.table_name, "error": str(e)})
            continue
        total_annotated += result.get("annotated", 0)
        total_skipped += result.get("skipped", 0)
        if result.get("table_annotated"):
            total_table_annotated += 1
        # 统计角色分布（基于本张表的最新结果）
        for c in table.columns:
            role = c.ai_semantic_role
            if role == "metric_candidate":
                total_metrics += 1
            elif role == "dimension_candidate":
                total_dims += 1
            elif role == "time_field":
                total_times += 1

    logger.info(
        f"自动标注完成: ds_id={ds_id}, tables={len(tables)} (已选), "
        f"annotated={total_annotated}, skipped={total_skipped}, "
        f"table_annotated={total_table_annotated}, "
        f"metrics={total_metrics}, dims={total_dims}, times={total_times}, "
        f"failed={len(failed_tables)}"
    )
    return {
        "ok": True,
        "metric_candidates": total_metrics,
        "dimension_candidates": total_dims,
        "time_fields": total_times,
        "tables_processed": len(tables),
        "table_annotated": total_table_annotated,
        "annotated": total_annotated,
        "skipped": total_skipped,
        "failed_tables": failed_tables,
    }


# ── YAML Import / Export ─────────────────────────────


@router.post("/{ds_id}/import-yaml")
def import_dataset_yaml(ds_id: int, payload: dict, db: Session = Depends(get_db)):
    """从 YAML 导入语义层配置（指标、维度、JOIN 关系）。"""
    logger.info(f"导入YAML: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    yaml_text = payload.get("yaml", "")
    if not yaml_text:
        raise HTTPException(status_code=400, detail="yaml 字段不能为空")

    try:
        data = yaml.safe_load(yaml_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"YAML 解析失败: {e}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="YAML 根节点必须是对象")

    # 更新 tables_json
    tables_json = {"tables": [], "joins": []}
    if "tables" in data:
        tables_json["tables"] = data["tables"]
    if "joins" in data:
        tables_json["joins"] = data["joins"]
    ds.tables_json = tables_json

    # 导入指标
    imported_metrics = 0
    if "metrics" in data:
        for mdata in data["metrics"]:
            name = mdata.get("name")
            existing = (
                db.query(models.SemanticMetric).filter_by(dataset_id=ds_id, name=name).first()
            )
            metric_payload = {
                "name": name,
                "display_name": mdata.get("display_name", name),
                "expr": mdata.get("expression") or mdata.get("expr", ""),
                "table_name": mdata.get("table") or mdata.get("table_name"),
                "time_field": mdata.get("time_field"),
                "granularity": mdata.get("granularity"),
                "format_str": mdata.get("format") or mdata.get("format_str"),
                "filter_sql": mdata.get("filter_sql")
                or (mdata.get("filters", [""])[0] if mdata.get("filters") else None),
                "synonyms": mdata.get("synonyms", []),
                "description": mdata.get("description"),
            }
            if existing:
                for key, value in metric_payload.items():
                    setattr(existing, key, value)
            else:
                db.add(models.SemanticMetric(dataset_id=ds_id, **metric_payload))
                imported_metrics += 1

    # 导入维度
    imported_dims = 0
    if "dimensions" in data:
        for ddata in data["dimensions"]:
            name = ddata.get("name")
            existing = (
                db.query(models.SemanticDimension).filter_by(dataset_id=ds_id, name=name).first()
            )
            dim_payload = {
                "name": name,
                "display_name": ddata.get("display_name", name),
                "column_name": ddata.get("column") or ddata.get("column_name", ""),
                "table_name": ddata.get("table") or ddata.get("table_name"),
                "join_to": ddata.get("join_to"),
                "join_key": ddata.get("join_key"),
                "hierarchy": ddata.get("hierarchy"),
                "enum_values": ddata.get("enum_values", []),
                "synonyms": ddata.get("synonyms", []),
            }
            if existing:
                for key, value in dim_payload.items():
                    setattr(existing, key, value)
            else:
                db.add(models.SemanticDimension(dataset_id=ds_id, **dim_payload))
                imported_dims += 1

    db.commit()
    logger.info(f"YAML导入成功: metrics={imported_metrics}, dims={imported_dims}")
    return {
        "ok": True,
        "metrics_imported": imported_metrics,
        "dimensions_imported": imported_dims,
        "tables_json_updated": bool(tables_json["tables"] or tables_json["joins"]),
    }


@router.get("/{ds_id}/export-yaml")
def export_dataset_yaml(ds_id: int, db: Session = Depends(get_db)):
    """将当前数据集的语义层配置导出为 YAML。"""
    logger.info(f"导出YAML: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    metrics = db.query(models.SemanticMetric).filter_by(dataset_id=ds_id).all()
    dimensions = db.query(models.SemanticDimension).filter_by(dataset_id=ds_id).all()

    tables_json = ds.tables_json or {}

    data = {
        "dataset": {
            "name": ds.name,
            "description": ds.description,
            "datasource_id": ds.datasource_id,
        },
        "tables": tables_json.get("tables", []),
        "joins": tables_json.get("joins", []),
        "metrics": [],
        "dimensions": [],
    }

    for m in metrics:
        data["metrics"].append(
            {
                "name": m.name,
                "display_name": m.display_name,
                "expression": m.expr,
                "table_name": m.table_name,
                "time_field": m.time_field,
                "filter_sql": m.filter_sql,
                "granularity": m.granularity,
                "format_str": m.format_str,
                "synonyms": m.synonyms or [],
                "description": m.description,
            }
        )

    for d in dimensions:
        data["dimensions"].append(
            {
                "name": d.name,
                "display_name": d.display_name,
                "column_name": d.column_name,
                "table_name": d.table_name,
                "join_to": d.join_to,
                "join_key": d.join_key,
                "hierarchy": d.hierarchy,
                "enum_values": d.enum_values or [],
                "synonyms": d.synonyms or [],
            }
        )

    yaml_text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    logger.info(f"YAML导出成功: ds_id={ds_id}")
    return {"yaml": yaml_text}


# ── Dataset Source Table Selection ───────────────────


@router.post("/{ds_id}/select-tables")
def select_tables_for_dataset(
    ds_id: int,
    payload: schemas.SelectTablesPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """批量选择 source_table 加入当前数据集，并异步触发 AI 标注。"""
    logger.info(f"选择表: ds_id={ds_id}, table_ids={payload.source_table_ids}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    added = 0
    added_table_ids = []
    for st_id in payload.source_table_ids:
        st = db.get(models.SourceTable, st_id)
        if not st:
            continue
        # 检查是否已存在
        existing = (
            db.query(models.DatasetSourceTable)
            .filter_by(dataset_id=ds_id, source_table_id=st_id)
            .first()
        )
        if not existing:
            db.add(models.DatasetSourceTable(dataset_id=ds_id, source_table_id=st_id))
            added += 1
            added_table_ids.append(st_id)

    db.commit()

    # 异步触发 AI 标注（只对新加入的表）
    if added_table_ids:
        from app.services.annotation import annotate_table_columns

        for st_id in added_table_ids:
            background_tasks.add_task(annotate_table_columns, db, st_id)
        logger.info(f"异步触发标注: tables={len(added_table_ids)}")

    logger.info(f"选择表完成: added={added}")
    return {"ok": True, "added": added}


@router.delete("/{ds_id}/select-tables/{source_table_id}")
def deselect_table_from_dataset(ds_id: int, source_table_id: int, db: Session = Depends(get_db)):
    """从数据集中移除某张 source_table。"""
    logger.info(f"移除表: ds_id={ds_id}, source_table_id={source_table_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    link = (
        db.query(models.DatasetSourceTable)
        .filter_by(dataset_id=ds_id, source_table_id=source_table_id)
        .first()
    )
    if link:
        db.delete(link)
        db.commit()
        logger.info(f"表移除成功: source_table_id={source_table_id}")
    return {"ok": True}


@router.get("/{ds_id}/selected-tables")
def list_selected_tables(ds_id: int, db: Session = Depends(get_db)):
    """获取数据集已选中的 source_table 列表。"""
    logger.info(f"获取已选表: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    links = db.query(models.DatasetSourceTable).filter_by(dataset_id=ds_id).all()
    result = []
    for link in links:
        st = link.source_table
        result.append(
            {
                "id": st.id,
                "dataset_link_id": link.id,
                "schema_name": st.schema_name,
                "table_name": st.table_name,
                "table_comment": st.table_comment,
                "ai_description": st.ai_description,
                "user_description": st.user_description,
                "effective_desc": st.effective_desc,
                "desc_source": st.desc_source,
                "annotated_at": st.annotated_at,
                "row_count_approx": st.row_count_approx,
                "column_count": len(st.columns),
            }
        )
    logger.info(f"返回 {len(result)} 个已选表")
    return result


@router.get("/{ds_id}/selected-columns")
def list_selected_columns(ds_id: int, db: Session = Depends(get_db)):
    """获取数据集所有已选表的字段（合并返回，含 table_name）。"""
    logger.info(f"获取已选字段: ds_id={ds_id}")
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        logger.warning(f"数据集不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据集不存在")

    links = db.query(models.DatasetSourceTable).filter_by(dataset_id=ds_id).all()
    result = []
    for link in links:
        st = link.source_table
        for col in st.columns:
            result.append(
                {
                    "id": col.id,
                    "source_table_id": st.id,
                    "table_name": st.table_name,
                    "schema_name": st.schema_name,
                    "column_name": col.column_name,
                    "data_type": col.data_type,
                    "column_comment": col.column_comment,
                    "business_desc": col.business_desc,
                    "ai_description": col.ai_description,
                    "ai_semantic_role": col.ai_semantic_role,
                    "ai_suggested_agg": col.ai_suggested_agg,
                    "user_description": col.user_description,
                    "user_semantic_role": col.user_semantic_role,
                    "effective_desc": col.effective_desc,
                    "desc_source": col.desc_source,
                    "annotated_at": col.annotated_at,
                    "is_nullable": col.is_nullable,
                    "column_default": col.column_default,
                    "ordinal_position": col.ordinal_position,
                    "semantic_role": col.semantic_role,
                    "default_agg": col.default_agg,
                    "sample_values": col.sample_values,
                }
            )
    # 按表名、字段位置排序
    result.sort(key=lambda c: (c["table_name"], c["ordinal_position"] or 0))
    logger.info(f"返回 {len(result)} 个字段")
    return result
