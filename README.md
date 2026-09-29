# 离线电子纸刷新规划 API

基于 Python + FastAPI 的离线刷新规划服务。给定**初始画面**与 **1～20 帧目标画面**
（均为同尺寸的 `0`/`1` 字符串网格，高、宽各 1～4），求总花费最低的逐帧刷新方案。

## 刷新规则

- 每个网格有一个“局刷次数”计数，初始全部为 `0`。
- **无变化帧**（与上一帧完全相同）只能 **跳过（skip）**，花费 `0`。
- **变化帧**可二选一：
  - **全刷 `full`**：花费 `full_cost`，并把所有网格的局刷次数清零；
  - **局刷 `partial`**：只刷新所有变化格的**最小轴对齐包围矩形**，
    花费 `矩形面积 × cell_cost`；矩形内**每一格（包括未变化格）**局刷次数加一，
    且矩形内任何格子的次数都**不得超过 `max_partial`（0～3）**，否则该帧不能局刷。
- 目标：总花费最低；总价相同时按逐帧模式序列字典序裁决，
  优先级 **`full` > `partial` > `skip`**（full 尽量靠前）。

## 一键启动（Docker Compose）

```bash
docker compose up --build -d
```

- 访问地址（本机）：`http://localhost:8000`
- 端口：`8000`（容器内 `8000`，如需改动改 `docker-compose.yml` 的端口映射）
- 接口文档（Swagger UI）：`http://localhost:8000/docs`
- 健康检查：`GET http://localhost:8000/health`

停止服务：

```bash
docker compose down
```

## 接口

`POST http://localhost:8000/plan`

请求体（JSON）：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `initial` | string[] | 初始画面，1～4 行，每行 1～4 个 `0`/`1` 字符 |
| `frames` | string[][] | 1～20 帧目标画面，尺寸必须与 `initial` 完全一致 |
| `max_partial` | int | `0～3`，每格允许的最大局刷次数（`0` 表示只能全刷变化帧） |
| `full_cost` | int | 正整数，全刷一次的花费 |
| `cell_cost` | int | 正整数，局刷矩形每格的花费 |

响应体（JSON）：

- `total_cost`：最低总花费（整数）
- `modes`：逐帧模式序列，元素为 `full` / `partial` / `skip`
- `plan`：逐帧明细
  - `index`：帧序号，从 `0` 开始
  - `mode`：`full` / `partial` / `skip`
  - `rect`：仅 `partial` 帧出现，零基闭区间 `{top, left, bottom, right}`
    （矩形包含 `top` 行、`left` 列到 `bottom` 行、`right` 列的所有格子）

非法输入（JSON 不合法、字段缺失/类型错、尺寸越界、字符非 `0/1`、
帧数不在 1～20、`max_partial` 越界、花费非正整数等）一律返回 **HTTP 422**，
响应为 `{"detail": "错误原因"}`。

## 可执行 HTTP 示例

### 示例 1：两帧均局刷

初始为 3×3 全 `0`；第 0 帧中格 `(0,1)` 变化，矩形为单格；
第 1 帧新增 `(1,1)` 变化，矩形仍为单格。各格计数不超过 `max_partial=2`，
总花费 `1×1 + 1×1 = 2`。

```bash
curl -s http://localhost:8000/plan \
  -H 'Content-Type: application/json' \
  -d '{
    "initial": ["000", "000", "000"],
    "frames": [["010", "000", "000"], ["010", "010", "000"]],
    "max_partial": 2,
    "full_cost": 5,
    "cell_cost": 1
  }'
```

返回：

```json
{
  "modes": ["partial", "partial"],
  "plan": [
    {"index": 0, "mode": "partial", "rect": {"top": 0, "left": 1, "bottom": 0, "right": 1}},
    {"index": 1, "mode": "partial", "rect": {"top": 1, "left": 1, "bottom": 1, "right": 1}}
  ],
  "total_cost": 2
}
```

### 示例 2：同价时 full 优先

1×1 画面，`full_cost = cell_cost = 1`，全刷与局刷同价（均为 1），
裁决规则选择 `full`：

```bash
curl -s http://localhost:8000/plan \
  -H 'Content-Type: application/json' \
  -d '{
    "initial": ["0"],
    "frames": [["1"]],
    "max_partial": 3,
    "full_cost": 1,
    "cell_cost": 1
  }'
```

返回：

```json
{
  "modes": ["full"],
  "plan": [
    {"index": 0, "mode": "full"}
  ],
  "total_cost": 1
}
```

### 示例 3：无变化帧跳过

```bash
curl -s http://localhost:8000/plan \
  -H 'Content-Type: application/json' \
  -d '{
    "initial": ["00", "00"],
    "frames": [["00", "00"], ["01", "00"], ["01", "00"]],
    "max_partial": 3,
    "full_cost": 10,
    "cell_cost": 1
  }'
```

返回（第 0、2 帧无变化，跳过；只对第 1 帧局刷单格，总花费 1）：

```json
{
  "modes": ["skip", "partial", "skip"],
  "plan": [
    {"index": 0, "mode": "skip"},
    {"index": 1, "mode": "partial", "rect": {"top": 0, "left": 1, "bottom": 0, "right": 1}},
    {"index": 2, "mode": "skip"}
  ],
  "total_cost": 1
}
```

### 示例 4：非法输入返回 422

`max_partial` 取值越界：

```bash
curl -i http://localhost:8000/plan \
  -H 'Content-Type: application/json' \
  -d '{
    "initial": ["0"],
    "frames": [["1"]],
    "max_partial": 9,
    "full_cost": 5,
    "cell_cost": 1
  }'
```

返回 `HTTP/1.1 422 Unprocessable Entity`：

```json
{"detail": "max_partial must be an integer in [0, 3]"}
```

## 实现说明

- 求解器位于 `app/planner.py`，不依赖 Web 框架，可单独调用与测试。
- 用动态规划逐帧推进，状态为每格的局刷次数向量；同状态合并时保留
  “花费更低、模式字典序更优”者。
- 每步做**计数支配剪枝**：若状态 A 的每格次数都不大于状态 B，且
  `(花费, 模式序列)` 不劣于 B，则 B 不可能带来更优后缀（A 能承受的
  后续局刷超集包含 B），直接丢弃。剪枝后前沿极小（每个“上次全刷位置”
  至多一个代表状态），4×4、20 帧的最坏情形也只需数毫秒。
