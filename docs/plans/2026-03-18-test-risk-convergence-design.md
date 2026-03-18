# 风险收敛三阶段异步化设计

**日期：** 2026-03-18

## 背景

当前“评审分析”“开发前分析”“提测前审计”三个按钮都是同步长请求。

- 前端全局请求超时为 15 秒，而 `review` 仍未单独覆盖长超时。
- 三个阶段都可能触发 LLM、产品知识检索、快照写库与风险台账更新。
- 页面刷新后无法恢复“正在执行”的状态，只能看到按钮 loading 消失或请求报错。

规则树生成已经完成了“异步启动 + 持久化进度 + 刷新恢复”的改造，这次目标是把三阶段分析也收敛到同类交互，但不引入规则树那种会话语义。

## 目标

- 将“评审分析”“开发前分析”“提测前审计”改为异步后台任务。
- 每个需求每个阶段只保留 1 条最新任务记录。
- 页面支持刷新恢复、失败恢复、中断展示。
- 保留当前 `RiskPanel` 的三块业务结果区，不改成会话式界面。
- 完成后继续复用现有快照、风险台账、正式输入的数据模型。

## 非目标

- 本期不引入 Celery、RQ 等外部任务系统。
- 本期不保留任务历史列表，不做多版本任务对比。
- 本期不做输入哈希缓存、结果复用或自动跳过重复分析。
- 本期不重做风险面板整体布局，只增加必要的任务状态展示。

## 方案选择

### 方案 A：复用规则树会话表

把这三个阶段也塞进 `rule_tree_sessions`。

优点：

- 表面上复用现有异步基础设施。

缺点：

- 会话表语义是“多轮对话 + 草稿快照 + 确认导入”。
- 风险收敛三阶段是“一次触发，一次结果”的任务模型。
- 混用后会让规则树和风险分析两个领域都出现无意义字段和状态分支。

### 方案 B：新增独立任务表

新增 `risk_analysis_tasks`，只承载任务状态、结果和关联快照。

优点：

- 数据模型与业务语义一致。
- 前端仍可复用“POST 启动 / GET 轮询 / 刷新恢复”的交互模式。
- 后续若要补任务历史或批量查询，也更容易扩展。

缺点：

- 需要新增模型、迁移、schema、service 和 API。

### 结论

采用 **方案 B**。这是最小的正确抽象，避免把规则树会话模型误用到风险分析任务上。

## 数据模型设计

新增表：`risk_analysis_tasks`

建议字段：

- `id`
- `requirement_id`
- `stage`：`review | pre_dev | pre_release`
- `status`：`queued | running | completed | failed | interrupted`
- `progress_message`
- `progress_percent`
- `last_error`
- `snapshot_id`：可空，关联 `effective_requirement_snapshots.id`
- `result_json`：JSON 字符串，存阶段结果
- `current_task_started_at`
- `current_task_finished_at`
- `created_at`
- `updated_at`

约束与语义：

- 每个需求每个阶段只保留 1 条任务记录。
- 若该阶段已有记录，再次启动时覆盖该记录的运行态字段和结果字段。
- 若该阶段已有 `running/queued` 任务，再次启动返回冲突，避免并发执行。

## 结果模型设计

`result_json` 按阶段存储，结构明确约定，不允许前端猜字段。

### `review`

```json
{
  "snapshot": {},
  "risks": [],
  "clarification_hints": []
}
```

### `pre_dev`

```json
{
  "snapshot": {},
  "risks": [],
  "conflicts": [],
  "matched_evidence": []
}
```

### `pre_release`

```json
{
  "closure_summary": "",
  "blocking_risks": [],
  "reopened_risks": [],
  "resolved_risks": [],
  "audit_notes": []
}
```

说明：

- `snapshot_id` 为可空外键，用于标记本次任务是否产生了新的有效需求快照。
- `snapshot` 仍写入 `result_json`，便于前端单接口恢复展示。
- `result_json.snapshot` 是只读冗余副本，真正的 source of truth 仍然是 `snapshot_id` 关联的 `effective_requirement_snapshots` 记录，避免后续维护时把它当成需要双向同步的主数据。
- `pre_release` 默认不生成新快照，因此 `snapshot_id` 允许为空。

## 后端接口设计

### 启动任务

`POST /api/requirements/{requirement_id}/analysis-tasks/{stage}`

行为：

- 校验需求存在。
- 校验 `stage` 合法。
- 若同阶段已有 `queued/running` 任务，返回 `409 Conflict`。
- 否则创建或覆盖该阶段最新任务：
  - `status = queued`
  - 清空 `last_error`
  - 保留 `snapshot_id` 和 `result_json`，直到新任务 `completed` 后再覆盖
  - 写入开始时间
- 启动后台线程后立即返回：

```json
{
  "accepted": true,
  "task": {}
}
```

### 获取单阶段最新任务

`GET /api/requirements/{requirement_id}/analysis-tasks/{stage}`

行为：

- 返回该需求该阶段的最新任务。
- 若不存在则返回 `null`。
- 前端用于按钮状态恢复、轮询和结果恢复。

### 获取三阶段任务汇总

`GET /api/requirements/{requirement_id}/analysis-tasks`

行为：

- 一次性返回三个阶段的最新任务映射，减少页面初始化时的 3 次请求。
- `RiskPanel` 初次加载和需求切换时优先使用该接口。

## 后端执行设计

采用 FastAPI 进程内后台线程，不引入队列系统。

### 状态推进

- `queued`：已接受任务，等待线程开始
- `running`：后台分析中
- `completed`：成功结束，结果已持久化
- `failed`：执行失败
- `interrupted`：服务重启导致中断

### 进度文案

三阶段统一用可信阶段进度，不伪造细粒度百分比：

- `queued` -> 5
- `running` -> 45
- `completed` -> 100
- `failed` -> 100
- `interrupted` -> 100

`progress_message` 由阶段决定：

- `review`: “正在生成评审快照”
- `pre_dev`: “正在执行开发前分析”
- `pre_release`: “正在执行提测前审计”

若后续需要细化 `running` 内部阶段，再扩展即可，本期不预埋复杂状态机。

### 任务执行逻辑

后台 worker 读取 `stage` 并路由到现有同步服务：

- `review` -> `backend/app/services/effective_requirement_service.py` 中的 `generate_review_snapshot`
- `pre_dev` -> `backend/app/services/predev_analyzer.py` 中的 `analyze_for_predev`
- `pre_release` -> `backend/app/services/prerelease_auditor.py` 中的 `audit_for_prerelease`

执行成功后：

- 若结果中包含快照，覆盖写入 `snapshot_id`
- 覆盖写入 `result_json`
- 更新 `status = completed`
- 写入完成时间

执行失败后：

- `status = failed`
- `last_error` 写入可读错误信息
- 保留上一轮成功结果，直到新的成功结果写入；因此任务重跑期间和失败后刷新页面都不应出现结果“闪空”

### 启动恢复

应用启动时扫描 `risk_analysis_tasks`：

- `queued/running` 统一改写为 `interrupted`
- `progress_message = 服务重启导致任务中断，请重新发起分析`
- `last_error` 同步写入相同文案

## 前端交互设计

保持 `RiskPanel` 当前业务布局不变，只改按钮行为和任务状态渲染。

### 按钮行为

- 点击阶段按钮后，立即乐观禁用该按钮。
- 调用 `POST /analysis-tasks/{stage}`。
- 成功后立刻显示该阶段“后台执行中”状态条。
- 若收到 `409`，提示“任务进行中”，并立即拉取该阶段最新任务。

### 页面初始化

需求切换或页面刷新时：

- 调用 `GET /analysis-tasks` 拉取三阶段汇总
- 恢复每个阶段的 `taskStatus`
- 若某阶段为 `queued/running`，只对当前激活阶段启动轮询
- 若用户切换关注阶段，先立即拉一次该阶段最新任务，再决定是否继续轮询

### 状态条位置

状态条放在各阶段结果区顶部，而不是做成全局单条。

原因：

- `review`、`pre_dev`、`pre_release` 的上次结果可能不同步更新。
- 用户可能一边看 `review` 的旧结果，一边等待 `pre_dev` 的新任务完成。

### 结果回填

前端状态拆成两层：

- `taskStatus`：当前任务运行态
- `lastSuccessResult`：最近一次成功结果

这样可以支持：

- 新任务执行中时继续展示旧结果
- 失败/中断时不闪空
- 新任务完成后再整体替换旧结果

回填规则：

- `review completed`：更新 `reviewResult` 和全局 `latestSnapshot`
- `pre_dev completed`：更新 `predevResult` 和全局 `latestSnapshot`
- `pre_release completed`：更新 `auditResult`；若 `snapshot_id == null`，`latestSnapshot` 保持不变

`latestSnapshot` 保持现有“全局最新快照”语义，不拆成三份状态。

### 轮询策略

- 默认轮询间隔 2 秒
- 连续进行中则逐步退避到 5 秒
- 终态停止轮询

策略与规则树保持接近，但不强行复用其页面内状态结构。

## 并发与覆盖语义

- 同一需求同一阶段只允许一个在途任务。
- 同一需求不同阶段允许并行，不做全局互斥。
- 同一阶段已有 `completed` 结果时，再次点击允许重跑：
  - 启动新任务
  - 旧结果继续展示
  - 新任务完成后覆盖旧结果

## 错误处理

- LLM 调用异常：`failed`
- 依赖前置条件不满足：
  - `pre_dev` 没有 review 快照
  - `pre_release` 没有有效快照
  这些仍写入 `failed`，并把错误信息回传到状态条
- 服务重启：`interrupted`
- 重复点击：返回 `409 Conflict`

前端失败态必须显示：

- 当前阶段
- 当前任务状态
- 错误文案
- 重试入口

## 测试策略

### 后端

- `POST` 立即返回，不阻塞等待任务完成
- 同阶段重复启动返回 `409`
- worker 成功后写入 `result_json/snapshot_id/completed`
- worker 失败后写入 `failed/last_error`
- 启动恢复将 `queued/running` 改为 `interrupted`
- 汇总接口正确返回三个阶段的最新任务

### 前端

当前仓库没有前端测试脚本，本期以前端构建和手工验收为主。

手工验收覆盖：

1. 点击阶段按钮后立即返回，不再出现长时间同步等待
2. 状态条显示“执行中”，旧结果仍可见
3. 刷新页面后任务状态恢复
4. 完成后结果替换成功，风险和输入列表刷新
5. 后端重启后页面显示“已中断”

## 实施结论

该方案保留了现有风险收敛面板的信息结构，同时把长耗时同步接口统一收敛成可恢复的异步任务流，能够直接解决当前 `review` 15 秒超时和三阶段缺乏进度恢复的问题。
