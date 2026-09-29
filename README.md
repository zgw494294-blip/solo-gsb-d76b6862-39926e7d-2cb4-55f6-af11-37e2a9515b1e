# E-Paper Refresh Planner（离线电子纸刷新规划 API）

给定初始画面与 1~20 帧目标画面（均为同尺寸 0/1 字符串行网格，高、宽各 1~4），在局刷次数上限 `max_partial`（0~3）约束下，求总花费最低的逐帧刷新方案。

## 规则

- 各格局刷次数初始为 0。
- **无变化帧只能跳过**（`skip`），花费 0，局刷次数不变。
- **变化帧**二选一：
  - **全刷 `full`**：花费 `full_cost`，所有格局刷次数清零；
  - **局刷 `partial`**：刷新变化格的**最小轴对齐包围矩形**，花费 `面积 × cell_cost`；矩形内**每格**（含未变格）局刷次数加一，且任何格次数不得超过 `max_partial`（`max_partial=0` 时局刷不可用）。
- 目标：总花费最低；**同价时按模式序列裁决，`full` 优先于 `partial`**（`skip` 位置由输入唯一确定）。

## 一键启动

```bash
docker compose up --build
```

（等价地：`docker build -t epaper-planner . && docker run -p 8000:8000 epaper-planner`）

- 访问地址：**http://localhost:8000**
- 端口：**8000**
- 交互式文档（Swagger UI）：http://localhost:8000/docs

## HTTP 示例

```bash
curl -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d '{
    "initial": ["00", "00"],
    "frames": [["11", "00"], ["11", "11"], ["00", "11"]],
    "max_partial": 2,
    "full_cost": 10,
    "cell_cost": 1
  }'
```

响应（`200 OK`）：

```json
{
  "total_cost": 6,
  "plan": [
    { "mode": "partial", "rect": { "top": 0, "left": 0, "bottom": 0, "right": 1 } },
    { "mode": "partial", "rect": { "top": 1, "left": 0, "bottom": 1, "right": 1 } },
    { "mode": "partial", "rect": { "top": 0, "left": 0, "bottom": 0, "right": 1 } }
  ]
}
```

## 接口说明

### `POST /plan`

请求体：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `initial` | `string[]` | 初始画面，1~4 行，每行 1~4 个 `0`/`1` 字符，等宽 |
| `frames` | `string[][]` | 1~20 帧目标画面，每帧尺寸与 `initial` 相同 |
| `max_partial` | `int` | 0~3，每格局刷次数上限 |
| `full_cost` | `int` | 正整数，全刷花费 |
| `cell_cost` | `int` | 正整数，局刷单格花费 |

响应体：

| 字段 | 说明 |
| --- | --- |
| `total_cost` | 最优方案总花费 |
| `plan[i].mode` | 第 i 帧模式：`skip` / `full` / `partial` |
| `plan[i].rect` | 局刷矩形 `(top, left, bottom, right)`，**零基闭区间**；仅 `partial` 时给出，其余为 `null` |

非法输入（尺寸越界、非法字符、帧数越界、尺寸不一致、参数越界或非正整数、JSON  malformed 等）一律返回 **`422 Unprocessable Entity`**。

## 本地开发与测试

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000   # 启动
python -m unittest discover -s tests              # 测试（含与暴力枚举对照的随机正确性测试）
```

## 实现要点

- 动态规划：状态为各格局刷次数向量（每格 0~`max_partial`），逐帧转移；
  每状态保留 `(累计花费, 模式序列)` 最小者——元组字典序天然实现
  “先比总花费，同价时 `full` 优先于 `partial`” 的裁决。
- 项目结构：
  - `app/solver.py` — 纯求解逻辑（不依赖 Web 框架）
  - `app/main.py` — FastAPI 入口、请求校验（Pydantic，非法输入 422）
  - `tests/` — 单元测试与 API 测试
