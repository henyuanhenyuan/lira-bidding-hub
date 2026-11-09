from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, db, finetune

router = APIRouter()


class DatasetIn(BaseModel):
    limit: int = Field(default=400, ge=20, le=2000)


class JobIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    base_model: str = "Qwen/Qwen3-4B"
    method: str = "lora"
    teacher: str = "qwen-plus"
    epochs: int = Field(default=2, ge=1, le=6)
    lr: float = Field(default=2e-4, gt=0, le=1e-2)
    dataset_path: str | None = None


@router.get("/api/finetune/stack")
def stack(actor: str = Depends(auth.require_role("admin", "manager"))) -> dict[str, Any]:
    return {
        **finetune.stack_status(),
        "latest_dataset": finetune.latest_dataset(),
        "teacher": "qwen-plus",
        "student": "Qwen/Qwen3-4B",
        "local_test": "qwen3:4b",
    }


@router.post("/api/finetune/dataset")
def build_dataset(
    body: DatasetIn,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return finetune.build_dataset(conn, limit=body.limit)


@router.get("/api/finetune/dataset")
def dataset(actor: str = Depends(auth.require_role("admin", "manager"))) -> dict[str, Any]:
    latest = finetune.latest_dataset()
    if not latest:
        raise HTTPException(404, "还没有数据集，请先生成")
    return latest


@router.get("/api/finetune/jobs")
def jobs(
    limit: int = 20,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return finetune.list_jobs(conn, limit)


@router.post("/api/finetune/jobs")
def create_job(
    body: JobIn,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    dataset_path = body.dataset_path
    if not dataset_path:
        latest = finetune.latest_dataset()
        if not latest:
            raise HTTPException(400, "还没有数据集，请先生成")
        dataset_path = latest["path"]
    with db.get_db() as conn:
        try:
            return finetune.create_job(
                conn,
                name=body.name.strip(),
                base_model=body.base_model.strip(),
                method=body.method,
                teacher=body.teacher.strip(),
                epochs=body.epochs,
                lr=body.lr,
                dataset_path=dataset_path,
                actor=actor,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/api/finetune/jobs/{job_id}")
def job_detail(
    job_id: str,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        try:
            return finetune.get_job(conn, job_id)
        except KeyError as exc:
            raise HTTPException(404, "微调任务不存在") from exc


@router.post("/api/finetune/jobs/{job_id}/validate")
def validate_job(
    job_id: str,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        try:
            return finetune.validate_job(conn, job_id)
        except KeyError as exc:
            raise HTTPException(404, "微调任务不存在") from exc
