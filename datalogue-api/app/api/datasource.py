# ============================================================
# File Name   : datasource.py
# Description:
#   数据源管理 API 端点。
#
# Responsibilities:
#   - 创建和测试数据源连接。
#   - 同步物理表结构并暴露表元数据。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# 数据源管理路由 — CRUD + 连接测试 + Schema 自动提取

from typing import List
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import encrypt_password
from app.core import schemas, models
from app.domains.data_source.service import (
    enrich_datasource_defaults,
    get_capabilities,
    get_schema,
    get_schemas,
    normalize_execution_dialect,
    preview_table,
    sync_source_tables,
    test_connection,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=List[schemas.DatasourceOut])
def list_datasources(db: Session = Depends(get_db)):
    """获取所有数据源列表。"""
    logger.info("获取数据源列表")
    result = db.query(models.Datasource).order_by(models.Datasource.id.desc()).all()
    logger.info(f"返回 {len(result)} 个数据源")
    return result


@router.get("/capabilities", response_model=List[schemas.DatasourceCapabilityOut])
def list_datasource_capabilities():
    """获取当前系统注册的数据源类型能力。"""
    return get_capabilities()


@router.post("", response_model=schemas.DatasourceOut)
def create_datasource(payload: schemas.DatasourceCreate, db: Session = Depends(get_db)):
    """创建新数据源，密码自动加密存储。"""
    logger.info(f"创建数据源: name={payload.name}, type={payload.db_type}")
    data = enrich_datasource_defaults(payload.model_dump())
    data["password_enc"] = encrypt_password(data.pop("password"))
    ds = models.Datasource(**data)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    logger.info(f"数据源创建成功: id={ds.id}")
    return ds


@router.get("/{ds_id}", response_model=schemas.DatasourceOut)
def get_datasource(ds_id: int, db: Session = Depends(get_db)):
    """获取单个数据源详情。"""
    logger.info(f"获取数据源详情: ds_id={ds_id}")
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        logger.warning(f"数据源不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ds


@router.put("/{ds_id}", response_model=schemas.DatasourceOut)
def update_datasource(ds_id: int, payload: schemas.DatasourceUpdate, db: Session = Depends(get_db)):
    """更新数据源信息。密码为空时不覆盖原密码。"""
    logger.info(f"更新数据源: ds_id={ds_id}")
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        logger.warning(f"数据源不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据源不存在")
    data = payload.model_dump(exclude_unset=True)
    if "db_type" in data:
        data = enrich_datasource_defaults(data)  # 切换数据源类型时补齐端口/驱动等服务端默认值。
    target_db_type = data.get("db_type", ds.db_type)
    target_dialect = data.get("dialect", ds.dialect)
    if target_db_type or target_dialect:
        data["dialect"] = normalize_execution_dialect(target_db_type, target_dialect)  # 部分更新也兜住 Doris 历史脏 dialect。
    if "password" in data:
        pwd = data.pop("password")
        if pwd:
            data["password_enc"] = encrypt_password(pwd)
    for key, value in data.items():
        setattr(ds, key, value)
    db.commit()
    db.refresh(ds)
    logger.info(f"数据源更新成功: ds_id={ds_id}")
    return ds


@router.delete("/{ds_id}")
def delete_datasource(ds_id: int, db: Session = Depends(get_db)):
    """删除数据源。"""
    logger.info(f"删除数据源: ds_id={ds_id}")
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        logger.warning(f"数据源不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据源不存在")
    db.delete(ds)
    db.commit()
    logger.info(f"数据源删除成功: ds_id={ds_id}")
    return {"ok": True}


@router.post("/{ds_id}/test")
def test_datasource(ds_id: int, db: Session = Depends(get_db)):
    """测试数据源连接，返回版本信息和连通性状态。"""
    logger.info(f"测试数据源连接: ds_id={ds_id}")
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        logger.warning(f"数据源不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据源不存在")
    result = test_connection(ds)
    ds.last_test_result = result
    ds.last_error_code = result.get("code")
    ds.last_error_message = None if result.get("ok") else result.get("message")
    ds.status = "connected" if result.get("ok") else "disconnected"
    db.commit()
    if not result.get("ok"):
        logger.error(f"数据源连接失败: ds_id={ds_id}, error={result.get('message')}")
        return result
    logger.info(f"数据源连接成功: ds_id={ds_id}, version={result.get('version')}")
    return result


@router.get("/{ds_id}/schemas")
def get_datasource_schemas(ds_id: int, db: Session = Depends(get_db)):
    """获取数据源中的所有 schema（MySQL 中为数据库列表）。"""
    logger.info(f"获取Schema列表: ds_id={ds_id}")
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        logger.warning(f"数据源不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据源不存在")
    try:
        schemas = get_schemas(ds)
    except Exception as e:
        logger.error(f"获取Schema列表失败: ds_id={ds_id}, error={e}")
        raise HTTPException(status_code=400, detail={"message": "获取 Schema 列表失败", "diagnostic": str(e)})
    logger.info(f"返回 {len(schemas)} 个schema")
    return {"schemas": schemas}


@router.get("/{ds_id}/schema")
def get_datasource_schema(ds_id: int, schema: str | None = None, db: Session = Depends(get_db)):
    """通过 SQLAlchemy inspect 自动提取指定 schema 的表、字段、主键和外键信息。"""
    logger.info(f"获取Schema详情: ds_id={ds_id}, schema={schema}")
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        logger.warning(f"数据源不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据源不存在")
    try:
        tables = get_schema(ds, schema_name=schema)
    except Exception as e:
        logger.error(f"获取Schema失败: ds_id={ds_id}, error={e}")
        raise HTTPException(status_code=400, detail={"message": "获取 Schema 失败", "diagnostic": str(e)})
    logger.info(f"返回 {len(tables)} 张表")
    return {"tables": tables}


@router.post("/{ds_id}/sync-tables")
def sync_datasource_tables(
    ds_id: int,
    schema: str | None = None,
    db: Session = Depends(get_db),
):
    """连接数据源，同步指定 Schema 的表结构到 source_table / source_column。"""
    logger.info(f"同步表结构: ds_id={ds_id}, schema={schema}")
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        logger.warning(f"数据源不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据源不存在")
    try:
        result = sync_source_tables(ds, schema_name=schema)
    except Exception as e:
        logger.error(f"同步表结构失败: ds_id={ds_id}, error={e}")
        raise HTTPException(status_code=400, detail={"message": "同步表结构失败", "diagnostic": str(e)})

    tables_data = result["tables"]
    synced_at = result["synced_at"]

    created_count = 0
    updated_count = 0

    for tdata in tables_data:
        # 查找或创建 SourceTable
        existing = (
            db.query(models.SourceTable)
            .filter_by(
                datasource_id=ds_id,
                schema_name=tdata["schema_name"],
                table_name=tdata["table_name"],
            )
            .first()
        )

        if existing:
            existing.table_comment = tdata.get("table_comment")
            existing.row_count_approx = tdata.get("row_count_approx")
            existing.synced_at = synced_at
            existing.status = "active"
            # 表注释变了 → 重新解析生效值
            from app.services.annotation import resolve_table_description

            existing.effective_desc, existing.desc_source = resolve_table_description(existing)
            table_obj = existing
            updated_count += 1
        else:
            table_obj = models.SourceTable(
                datasource_id=ds_id,
                schema_name=tdata["schema_name"],
                table_name=tdata["table_name"],
                table_comment=tdata.get("table_comment"),
                row_count_approx=tdata.get("row_count_approx"),
                synced_at=synced_at,
                status="active",
                desc_source="unknown",
            )
            db.add(table_obj)
            db.flush()
            created_count += 1

        # ── 增量合并字段：保留已有标注，只更新 DDL 元数据 ──

        # 1. 获取现有字段映射
        existing_cols = {
            c.column_name: c
            for c in db.query(models.SourceColumn).filter_by(table_id=table_obj.id).all()
        }
        fresh_col_names = set()

        for cdata in tdata["columns"]:
            col_name = cdata["column_name"]
            fresh_col_names.add(col_name)
            db_comment = cdata.get("column_comment")

            if col_name in existing_cols:
                col = existing_cols[col_name]
                # 只更新 DDL 元数据，保留标注字段
                col.data_type = cdata.get("data_type")
                col.is_nullable = cdata.get("is_nullable")
                col.column_default = cdata.get("column_default")
                col.ordinal_position = cdata.get("ordinal_position")
                col.sample_values = cdata.get("sample_values")

                # column_comment 变化时更新并标记 stale
                old_comment = (col.column_comment or "").strip()
                new_comment = (db_comment or "").strip()
                if old_comment != new_comment:
                    col.column_comment = db_comment
                    # 如果当前生效值来自 DB 注释，标记为 stale 以待重新标注
                    if col.desc_source in ("db_comment", "unknown"):
                        col.desc_source = "stale"
            else:
                # 新字段
                col = models.SourceColumn(
                    table_id=table_obj.id,
                    column_name=col_name,
                    data_type=cdata.get("data_type"),
                    column_comment=db_comment,
                    is_nullable=cdata.get("is_nullable"),
                    column_default=cdata.get("column_default"),
                    ordinal_position=cdata.get("ordinal_position"),
                    sample_values=cdata.get("sample_values"),
                    desc_source="unknown",
                )
                db.add(col)

        # 2. 删除数据库中已不存在的字段
        stale_cols = (
            db.query(models.SourceColumn)
            .filter_by(table_id=table_obj.id)
            .filter(~models.SourceColumn.column_name.in_(fresh_col_names))
            .all()
        )
        for stale in stale_cols:
            db.delete(stale)

    db.commit()
    logger.info(
        f"同步完成: created={created_count}, updated={updated_count}, total={len(tables_data)}"
    )
    return {
        "ok": True,
        "created": created_count,
        "updated": updated_count,
        "total_tables": len(tables_data),
        "skipped": result.get("skipped", []),
        "errors": result.get("errors", []),
    }


@router.get("/{ds_id}/source-tables")
def list_datasource_source_tables(ds_id: int, schema: str | None = None, db: Session = Depends(get_db)):
    """获取数据源下已同步的 source_table 列表。"""
    logger.info(f"获取数据源表列表: ds_id={ds_id}, schema={schema}")
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        logger.warning(f"数据源不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据源不存在")
    q = db.query(models.SourceTable).filter_by(datasource_id=ds_id)
    if schema:
        q = q.filter_by(schema_name=schema)
    tables = q.order_by(models.SourceTable.schema_name, models.SourceTable.table_name).all()

    # 计算每个表的字段数
    result = []
    for t in tables:
        result.append(
            {
                "id": t.id,
                "datasource_id": t.datasource_id,
                "schema_name": t.schema_name,
                "table_name": t.table_name,
                "table_comment": t.table_comment,
                "business_desc": t.business_desc,
                "ai_description": t.ai_description,
                "user_description": t.user_description,
                "effective_desc": t.effective_desc,
                "desc_source": t.desc_source,
                "annotated_at": t.annotated_at,
                "row_count_approx": t.row_count_approx,
                "status": t.status,
                "synced_at": t.synced_at,
                "column_count": len(t.columns),
            }
        )
    logger.info(f"返回 {len(result)} 张表")
    return result


@router.get("/source-table/{table_id}/columns")
def list_source_table_columns(table_id: int, db: Session = Depends(get_db)):
    """获取指定 source_table 的所有字段（含 LLM 标注结果）。"""
    logger.info(f"获取表字段: table_id={table_id}")
    table = db.get(models.SourceTable, table_id)
    if not table:
        logger.warning(f"表不存在: table_id={table_id}")
        raise HTTPException(status_code=404, detail="表不存在")
    result = [schemas.SourceColumnOut.model_validate(c) for c in table.columns]
    logger.info(f"返回 {len(result)} 个字段")
    return result


@router.put("/source-column/{column_id}")
def update_source_column(
    column_id: int, payload: schemas.SourceColumnUpdate, db: Session = Depends(get_db)
):
    """更新单个 source_column 的用户标注。"""
    logger.info(f"更新字段标注: column_id={column_id}")
    col = db.get(models.SourceColumn, column_id)
    if not col:
        raise HTTPException(status_code=404, detail="字段不存在")

    from app.services.annotation import resolve_description

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(col, key, value)

    # 重新解析生效值
    col.effective_desc, col.desc_source = resolve_description(col)
    if "user_description" in data or "user_semantic_role" in data:
        col.review_status = "confirmed"
        col.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(col)
    logger.info(f"字段标注更新成功: column_id={column_id}, desc_source={col.desc_source}")
    return schemas.SourceColumnOut.model_validate(col)


@router.post("/source-table/{table_id}/annotate")
def trigger_source_table_annotation(
    table_id: int, force: bool = False, db: Session = Depends(get_db)
):
    """手动触发单张表的 AI 标注。幂等：已标注字段默认跳过，force=true 强制重标。"""
    logger.info(f"手动触发标注: table_id={table_id}, force={force}")
    table = db.get(models.SourceTable, table_id)
    if not table:
        raise HTTPException(status_code=404, detail="表不存在")

    from app.services.annotation import annotate_table_columns

    result = annotate_table_columns(db, table_id, force=force)
    if result["failed"] and result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/{ds_id}/preview")
def preview_datasource_table(ds_id: int, payload: dict, db: Session = Depends(get_db)):
    """从数据源实时查询某张表的前 N 条数据。"""
    logger.info(f"预览表数据: ds_id={ds_id}, payload={payload}")
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        logger.warning(f"数据源不存在: ds_id={ds_id}")
        raise HTTPException(status_code=404, detail="数据源不存在")

    schema = payload.get("schema", "public")
    table = payload.get("table")
    limit = payload.get("limit", 5)
    if not table:
        raise HTTPException(status_code=400, detail="table 字段不能为空")

    try:
        return preview_table(ds, schema, table, limit)
    except Exception as e:
        logger.error(f"预览查询失败: ds_id={ds_id}, error={e}")
        raise HTTPException(status_code=400, detail={"message": "查询失败", "diagnostic": str(e)})
