from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app import schemas, models

router = APIRouter()


@router.get("", response_model=List[schemas.DatasetOut])
def list_datasets(datasource_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(models.SemanticDataset)
    if datasource_id:
        q = q.filter(models.SemanticDataset.datasource_id == datasource_id)
    return q.order_by(models.SemanticDataset.id.desc()).all()


@router.post("", response_model=schemas.DatasetOut)
def create_dataset(payload: schemas.DatasetCreate, db: Session = Depends(get_db)):
    ds = models.SemanticDataset(**payload.model_dump())
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


@router.get("/{ds_id}", response_model=schemas.DatasetOut)
def get_dataset(ds_id: int, db: Session = Depends(get_db)):
    """获取单个数据集详情。"""
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据集不存在")
    return ds


@router.put("/{ds_id}", response_model=schemas.DatasetOut)
def update_dataset(ds_id: int, payload: schemas.DatasetCreate, db: Session = Depends(get_db)):
    """更新数据集信息。"""
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据集不存在")
    for key, value in payload.model_dump().items():
        setattr(ds, key, value)
    db.commit()
    db.refresh(ds)
    return ds


@router.delete("/{ds_id}")
def delete_dataset(ds_id: int, db: Session = Depends(get_db)):
    """删除数据集及其关联的指标和维度。"""
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据集不存在")
    # 级联删除关联的指标和维度
    db.query(models.SemanticMetric).filter(models.SemanticMetric.dataset_id == ds_id).delete()
    db.query(models.SemanticDimension).filter(models.SemanticDimension.dataset_id == ds_id).delete()
    db.delete(ds)
    db.commit()
    return {"ok": True}


@router.post("/{ds_id}/metric", response_model=schemas.MetricOut)
def add_metric(ds_id: int, payload: schemas.MetricCreate, db: Session = Depends(get_db)):
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据集不存在")
    m = models.SemanticMetric(dataset_id=ds_id, **payload.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.post("/{ds_id}/dimension", response_model=schemas.DimensionOut)
def add_dimension(ds_id: int, payload: schemas.DimensionCreate, db: Session = Depends(get_db)):
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据集不存在")
    d = models.SemanticDimension(dataset_id=ds_id, **payload.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.post("/{ds_id}/embed")
def embed_dataset(ds_id: int, db: Session = Depends(get_db)):
    ds = db.get(models.SemanticDataset, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="数据集不存在")
    # TODO: 调用 embedding 服务生成 schema embedding
    return {"ok": True, "message": "embedding 任务已提交"}


@router.get("/{ds_id}/metrics", response_model=List[schemas.MetricOut])
def list_metrics(ds_id: int, db: Session = Depends(get_db)):
    """获取数据集下的所有指标。"""
    return db.query(models.SemanticMetric).filter(models.SemanticMetric.dataset_id == ds_id).all()


@router.delete("/{ds_id}/metric/{mid}")
def delete_metric(ds_id: int, mid: int, db: Session = Depends(get_db)):
    """删除指标。"""
    m = db.get(models.SemanticMetric, mid)
    if not m or m.dataset_id != ds_id:
        raise HTTPException(status_code=404, detail="指标不存在")
    db.delete(m)
    db.commit()
    return {"ok": True}


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
    d = db.get(models.SemanticDimension, did)
    if not d or d.dataset_id != ds_id:
        raise HTTPException(status_code=404, detail="维度不存在")
    db.delete(d)
    db.commit()
    return {"ok": True}
