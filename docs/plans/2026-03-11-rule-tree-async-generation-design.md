# 规则树异步生成与可恢复进度设计

**日期：** 2026-03-11

## 背景

当前规则树会话生成接口 `POST /api/rules/sessions/{session_id}/generate` 为同步长请求。生成链路包含两段串行 LLM 调用：

1. 规则树生成
2. 自审与修正

当需求文本较长时，前端请求容易先于后端处理完成而超时。现有页面只有按钮级 `loading`，用户无法判断当前阶段，也无法在刷新页面、关闭浏览器后恢复查看进度。

## 目标

- 将规则树会话生成改为异步后台任务。
- 进度状态持久化到数据库，支持刷新页面和关闭浏览器后恢复查看。
- 页面以阶段式进度展示任务所处阶段，而不是仅显示一个长时间转圈。
- 任务完成后保留结果，用户重新进入会话仍能看到最终生成结果。
- 后端服务重启后，未完成任务允许中断，但页面必须能看到其已中断。

## 非目标

- 本期不引入 Celery、RQ 等独立任务队列系统。
- 本期不要求服务重启后自动续跑未完成任务。
- 本期不实现精确百分比进度，只展示可信的阶段进度。
- 本期不改造增量更新接口为异步，优先覆盖首次生成链路。

## 方案选择

### 方案 A：复用 `RuleTreeSession` 作为异步任务载体

在现有 `rule_tree_sessions` 表上扩展状态、进度和结果字段。`generate` 接口负责启动后台任务，任务执行状态回写到当前 session。

优点：

- 与现有会话模型一致，前端改造成本最低。
- 刷新恢复逻辑天然以 `session_id` 为主键。
- 不需要额外引入 task 概念。

缺点：

- 一条 session 当前只适合承载一轮“当前生成任务”状态。
- 若未来需要保留完整的任务历史，可能需要再拆出独立任务表。

### 方案 B：新增 `RuleTreeTask` 表

将会话和任务拆开，一条 session 下可挂多条历史任务。

优点：

- 状态机更清晰，历史保留更完整。

缺点：

- 当前需求下属于过度设计，前后端概念都会变复杂。

### 结论

采用 **方案 A**。当前目标是快速解决同步超时和可恢复进度问题，复用 `RuleTreeSession` 足够，并且与现有代码结构最匹配。

## 后端设计

### 1. 状态模型

扩展 `RuleTreeSessionStatus`，建议新增：

- `generating`
- `reviewing`
- `saving`
- `completed`
- `failed`
- `interrupted`

保留现有：

- `active`
- `confirmed`
- `archived`

说明：

- `active` 表示已创建但尚未开始生成。
- `completed` 表示本轮生成成功并已持久化结果，可供前端直接恢复展示。
- `interrupted` 表示服务重启或异常退出后，原本运行中的任务未正常结束。

### 2. Session 持久化字段

在 `rule_tree_sessions` 增加以下字段：

- `progress_stage`: 阶段码，例如 `queued/generating/reviewing/saving/completed/failed/interrupted`
- `progress_message`: 给前端展示的中文说明
- `progress_percent`: 阶段映射的固定百分比
- `last_error`: 最近一次失败或中断原因
- `generated_tree_snapshot`: 生成阶段结果快照
- `reviewed_tree_snapshot`: 自审后结果快照
- `current_task_started_at`
- `current_task_finished_at`

这些字段都需要序列化到 `RuleTreeSessionRead` 中，以便列表页和详情页都能恢复。

### 3. 接口改造

#### `POST /api/rules/sessions/{session_id}/generate`

改为“启动任务”接口：

- 校验 session 状态
- 持久化本次输入的 `requirement_text/title/image`
- 将 session 状态更新为 `generating`
- 立即返回当前 session 状态，不阻塞等待结果
- 启动后台任务执行生成流程

建议响应体增加：

- `accepted: true`
- `session`

#### `GET /api/rules/sessions/{session_id}`

沿用现有详情接口，但返回扩展后的 session 状态与结果快照：

- 进行中：前端据此恢复轮询
- 已完成：前端可恢复结果展示
- 已失败/中断：前端展示错误态与重试入口

本期不强制新增单独的 status endpoint，优先复用详情接口减少接口面。

### 4. 后台执行方式

使用 FastAPI 进程内后台线程执行，不引入外部队列：

- 请求线程负责落库并启动后台任务
- 后台任务内部按阶段更新 session 状态
- 每个阶段完成后立即提交数据库

阶段顺序：

1. `queued`
2. `generating`
3. `reviewing`
4. `saving`
5. `completed`

失败时：

- `status = failed`
- `progress_stage = failed`
- `last_error` 写入用户可读错误
- 保留已存在的历史消息和阶段快照

### 5. 并发与幂等

同一 session 在 `generating/reviewing/saving` 中时：

- 禁止再次发起 `generate`
- 返回 409 或 400，提示“当前会话生成中”

同一 requirement 下的不同 session：

- 允许并行，保持与当前会话模型一致

### 6. 服务重启后的中断恢复

服务启动时扫描 `rule_tree_sessions`：

- 若状态为 `generating/reviewing/saving`
- 统一改为 `interrupted`
- `progress_stage = interrupted`
- `progress_message = 服务重启导致任务中断，请重新发起生成`

这样前端重新打开页面时不会永远看到“进行中”假状态。

## 前端设计

### 1. 交互流程

点击“开始生成”后：

1. 调用启动接口
2. 立即进入轮询模式
3. 展示进度区，不再等待长连接返回

页面刷新或重新打开后：

1. 重新拉取 session 详情
2. 如果 session 状态为 `generating/reviewing/saving`，自动恢复轮询
3. 如果状态为 `completed`，恢复结果卡片和树数据
4. 如果状态为 `failed/interrupted`，恢复失败提示和重试按钮

### 2. 进度展示

使用“阶段条 + 文案”，不展示伪精确数值。

推荐阶段映射：

- `queued` -> 5%
- `generating` -> 45%
- `reviewing` -> 80%
- `saving` -> 95%
- `completed` -> 100%

页面展示：

- `Steps` 或 `Progress` 组件展示阶段
- 文案区域展示 `progress_message`
- 失败时展示 `last_error`

### 3. 结果恢复

当前前端结果依赖同步接口返回的 `sessionGenerateResult`。异步化后改为：

- 优先从 `session.reviewed_tree_snapshot`
- 次级从 `session.generated_tree_snapshot`
- `diff` 可在完成时由后端持久化，或前端收到 completed 状态后重新拉完整结果

为降低改造成本，建议后端在 session 详情中直接返回可恢复的 diff 与树快照，避免前端再次拼装。

## 数据流

### 启动任务

前端 `POST /generate` -> 后端落库并返回 `accepted` -> 前端开始轮询 `GET /sessions/{id}`

### 任务执行

后台线程按阶段更新：

- 状态
- 进度文案
- 树快照
- 错误信息
- 完成时间

### 页面恢复

进入会话页 -> 拉取 session detail -> 根据状态恢复 UI

## 错误处理

- LLM 调用异常：标记 `failed`
- JSON 解析异常：标记 `failed`
- 后端服务重启：启动时批量标记 `interrupted`
- 用户重复点击：返回“会话生成中”

前端错误态必须包含：

- 当前阶段
- 错误原因
- 重新发起生成入口

## 测试策略

### 后端

- 启动生成后接口立即返回，不阻塞等待 LLM 完成
- 后台任务按顺序推进状态
- 成功后 session 持久化树快照与完成状态
- 失败后 session 标记为 `failed` 并记录错误
- 服务启动恢复逻辑可将进行中的 session 标记为 `interrupted`
- 重复启动同一 session 时返回冲突

### 前端

- 启动生成后进入轮询
- `generating/reviewing/saving` 状态时显示进度条与文案
- 刷新页面后能恢复进行中状态
- `completed` 后能恢复生成结果区域
- `failed/interrupted` 后显示错误提示和重试按钮

## 风险与取舍

- 进程内后台线程不适合横向扩展部署，但符合当前单机场景。
- 若未来需要真正可靠的任务执行和服务重启续跑，应再演进为独立任务队列。
- 本期先解决最核心的同步超时和进度恢复，不扩大到所有 LLM 接口。
