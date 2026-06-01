# 数据源管理路由 — CRUD + 连接测试 + Schema 自动提取

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import encrypt_password
from app import schemas, models
from app.services.datasource import test_connection, get_schema, get_schemas

router = APIRouter()


@router.get("", response_model=List[schemas.DatasourceOut])
def list_datasources(db: Session = Depends(get_db)):
    """获取所有数据源列表。"""
    return db.query(models.Datasource).order_by(models.Datasource.id.desc()).all()


@router.post("", response_model=schemas.DatasourceOut)
def create_datasource(payload: schemas.DatasourceCreate, db: Session = Depends(get_db)):
    """创建新数据源，密码自动加密存储。"""
    data = payload.model_dump()
    data["password_enc"] = encrypt_password(data.pop("password"))
    ds = models.Datasource(**data)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


@router.get("/{ds_id}", response_model=schemas.DatasourceOut)
def get_datasource(ds_id: int, db: Session = Depends(get_db)):
    """获取单个数据源详情。"""
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ds


@router.put("/{ds_id}", response_model=schemas.DatasourceOut)
def update_datasource(ds_id: int, payload: schemas.DatasourceUpdate, db: Session = Depends(get_db)):
    """更新数据源信息。密码为空时不覆盖原密码。"""
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        pwd = data.pop("password")
        if pwd:
            data["password_enc"] = encrypt_password(pwd)
    for key, value in data.items():
        setattr(ds, key, value)
    db.commit()
    db.refresh(ds)
    return ds


@router.delete("/{ds_id}")
def delete_datasource(ds_id: int, db: Session = Depends(get_db)):
    """删除数据源。"""
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    db.delete(ds)
    db.commit()
    return {"ok": True}


@router.post("/{ds_id}/test")
def test_datasource(ds_id: int, db: Session = Depends(get_db)):
    """测试数据源连接，返回版本信息和连通性状态。"""
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    result = test_connection(ds)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    # 连接成功则更新状态
    ds.status = "connected"  # type: ignore[assignment]
    db.commit()
    return result


@router.get("/{ds_id}/schemas")
def get_datasource_schemas(ds_id: int, db: Session = Depends(get_db)):
    """获取数据源中的所有 schema（MySQL 中为数据库列表）。"""
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    try:
        schemas = get_schemas(ds)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"获取 Schema 列表失败: {e}")
    return {"schemas": schemas}


@router.get("/{ds_id}/schema")
def get_datasource_schema(ds_id: int, schema: str = None, db: Session = Depends(get_db)):
    """通过 SQLAlchemy inspect 自动提取指定 schema 的表、字段、主键和外键信息。"""
    ds = db.get(models.Datasource, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    try:
        tables = get_schema(ds, schema_name=schema)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"获取 Schema 失败: {e}")
    return {"tables": tables}
