"""离线电子纸刷新规划 HTTP API (FastAPI)。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator, model_validator

from app.solver import solve_plan

app = FastAPI(title="E-Paper Refresh Planner", version="1.0.0")


def _validate_grid(grid: List[str], name: str) -> List[str]:
    if not 1 <= len(grid) <= 4:
        raise ValueError(f"{name}: 网格高度须为 1~4 行")
    width = len(grid[0])
    if not 1 <= width <= 4:
        raise ValueError(f"{name}: 网格宽度须为 1~4 列")
    for row in grid:
        if len(row) != width:
            raise ValueError(f"{name}: 各行宽度必须一致")
        if any(ch not in "01" for ch in row):
            raise ValueError(f"{name}: 网格只能包含字符 '0' 和 '1'")
    return grid


class PlanRequest(BaseModel):
    initial: List[str] = Field(description="初始画面, 0/1 字符串行网格")
    frames: List[List[str]] = Field(description="1~20 帧目标画面")
    max_partial: int = Field(strict=True, ge=0, le=3, description="每格局刷次数上限 0~3")
    full_cost: int = Field(strict=True, gt=0, description="全刷花费, 正整数")
    cell_cost: int = Field(strict=True, gt=0, description="局刷单格花费, 正整数")

    @field_validator("initial")
    @classmethod
    def _check_initial(cls, grid: List[str]) -> List[str]:
        return _validate_grid(grid, "initial")

    @field_validator("frames")
    @classmethod
    def _check_frames(cls, frames: List[List[str]]) -> List[List[str]]:
        if not 1 <= len(frames) <= 20:
            raise ValueError("frames: 目标帧数须为 1~20")
        for i, grid in enumerate(frames):
            _validate_grid(grid, f"frames[{i}]")
        return frames

    @model_validator(mode="after")
    def _check_same_dimensions(self) -> "PlanRequest":
        height, width = len(self.initial), len(self.initial[0])
        for i, grid in enumerate(self.frames):
            if len(grid) != height or any(len(row) != width for row in grid):
                raise ValueError(f"frames[{i}]: 所有画面尺寸必须与 initial 一致 ({height}x{width})")
        return self


class Rect(BaseModel):
    top: int
    left: int
    bottom: int
    right: int


class Step(BaseModel):
    mode: str = Field(description="skip / full / partial")
    rect: Optional[Rect] = Field(default=None, description="局刷矩形 (top,left,bottom,right) 零基闭区间, 仅 partial 时给出")


class PlanResponse(BaseModel):
    total_cost: int
    plan: List[Step]


@app.get("/")
def root() -> dict:
    return {"service": "e-paper-refresh-planner", "plan_endpoint": "POST /plan", "docs": "/docs"}


@app.post("/plan", response_model=PlanResponse)
def plan(req: PlanRequest) -> dict:
    return solve_plan(
        initial=req.initial,
        frames=req.frames,
        max_partial=req.max_partial,
        full_cost=req.full_cost,
        cell_cost=req.cell_cost,
    )
