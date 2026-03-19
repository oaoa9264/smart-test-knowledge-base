# 需求快照新鲜度与规范化 PRD 导出设计

**日期：** 2026-03-19

## 背景

当前 `review / pre_dev / pre_release` 三阶段能力依赖“最新有效需求快照”作为统一口径，但系统没有明确表达“这份快照是否仍然基于最新输入”。

这带来两个实际问题：

1. 用户修改了原始需求或补充了正式输入后，如果没有重新执行分析，页面仍然展示旧快照，容易被误认为当前有效口径。
2. 风险澄清沉淀进 `RequirementInput` 后，用户希望把“当前需求”整理成一份更规范、可导出的 PRD，但现有系统只有快照和产品文档更新建议，没有“当前需求导出”能力。

## 目标

- 明确判断有效需求快照是否已过期，并在前后端统一提示。
- 阻止 `pre_dev` 和 `pre_release` 在使用过期快照时继续执行。
- 新增“当前需求规范化文档”能力，支持页面预览和 Markdown 下载。
- 导出文档只保留以下结构：
  - `# 需求标题`
  - `## 1. 需求背景与目标`
  - `## 2. 主流程`
  - `## 3. 异常与边界场景`
  - `## 4. 约束与兼容性`
  - `## 5. 待确认事项`
- 文档正文只允许放“已明确内容”；所有不确定、推断、缺失、冲突信息统一放入 `## 5. 待确认事项`。

## 非目标

- 本期不自动在输入变更后后台重跑 `review / pre_dev / pre_release`。
- 本期不生成 Word/Docx。
- 本期不把“规范化需求文档”直接写回产品文档库。
- 本期不把原始需求详情页整体改版，只增加必要入口和提示。

## 方案选择

### 方案 A：引入 `content_revision`

在 `Requirement` 上维护统一递增版本号，在快照上记录 `basis_revision`，前后端通过数值对比判断是否过期。

优点：

- 判断简单直接。
- 未来如果更多字段影响“过期”语义，扩展成本低。

缺点：

- 需要在所有写入口维护递增逻辑。
- 当前系统里影响快照的输入分布在 `Requirement.raw_text` 和 `RequirementInput` 两类数据上，侵入面较大。

### 方案 B：`based_on_input_ids + basis_hash`

保留现有 `based_on_input_ids` 作为可解释性记录，同时新增 `basis_hash`，对所有会影响快照新鲜度的输入做稳定序列化并计算哈希。

优点：

- 不需要引入全局递增计数器。
- 能覆盖“输入内容被原地修改但 ID 不变”的情况。
- `based_on_input_ids` 仍可保留“这份快照基于哪些输入生成”的解释能力。

缺点：

- 需要新增统一哈希函数和快照校验逻辑。

### 结论

采用 **方案 B**：

- `based_on_input_ids` 负责可解释性。
- `basis_hash` 负责过期判定。

## 快照新鲜度设计

### 统一哈希函数

在 `backend/app/services/effective_requirement_service.py` 中新增统一函数：

```python
def compute_basis_hash(requirement: Requirement, inputs: List[RequirementInput]) -> str:
    """Deterministic hash of all sources that affect snapshot freshness."""
```

哈希输入范围：

- `requirement.raw_text`
- 当前 requirement 下全部 `RequirementInput`

`RequirementInput` 的稳定序列化至少包含：

- `input_type`
- `content`
- `source_label`

排序要求：

- 按稳定顺序序列化，避免数据库返回顺序差异导致 hash 漂移。
- 推荐排序键：`created_at`, `id`；若实现上更稳，也可直接按 `id`。

### 数据模型

在 `EffectiveRequirementSnapshot` 上新增字段：

- `basis_hash`

保留现有字段：

- `based_on_input_ids`

语义划分：

- `based_on_input_ids`：快照生成时使用了哪些输入记录 ID
- `basis_hash`：快照生成时完整输入面的签名

### 生成快照时的写入规则

`review` 快照生成时：

- 查询当前全部 `RequirementInput`
- 生成 `based_on_input_ids`
- 计算 `basis_hash`
- 一并写入新快照

`pre_dev` 快照生成时：

- 基于当前输入重新计算 `basis_hash`
- 继续写入 `based_on_input_ids`
- `base_snapshot_id` 仍保留对上游快照的引用

这样 `review` 与 `pre_dev` 两类快照都具备独立的新鲜度判断能力。

### 过期判断规则

新增统一函数，例如：

```python
def is_snapshot_stale(
    requirement: Requirement,
    inputs: List[RequirementInput],
    snapshot: EffectiveRequirementSnapshot,
) -> bool:
```

判断规则：

- 重新计算当前 `basis_hash`
- 与 `snapshot.basis_hash` 比较
- 不一致即视为 `stale`

`based_on_input_ids` 不参与最终布尔判定，只用于调试、展示和可解释性。

### API 输出

现有 `EffectiveSnapshotRead` 建议新增：

- `basis_hash`
- `is_stale`

如果前端需要展示“当前口径”，也可额外返回：

- `current_basis_hash`

但这不是必须项；只要返回 `is_stale` 即可满足 UI 判断。

### 后端错误语义

不要把错误码塞进 `ValueError.message` 再由 API 层拆字符串。

建议新增显式异常类型，例如：

- `NoSnapshotError`
- `StaleSnapshotError`

服务层规则：

- `analyze_for_predev()` / `audit_for_prerelease()` 在语义明确的场景下抛自定义异常
- 其他通用业务错误仍可继续使用 `ValueError`

API 层规则：

- 单独 catch `NoSnapshotError`
- 单独 catch `StaleSnapshotError`
- 兜底再 catch `ValueError`

这样既能返回结构化错误，又不会破坏现有其他 `ValueError -> detail=str(exc)` 的兼容语义。

结构化错误建议返回：

```json
{
  "detail": {
    "code": "STALE_SNAPSHOT",
    "message": "需求已变更，请先重新执行评审分析。"
  }
}
```

`pre_dev` 校验逻辑：

- 继续要求存在可用基线快照
- 取实际参与分析的最新 `review/pre_dev` 快照
- 若该快照已过期，拒绝执行

`pre_release` 校验逻辑：

- 取审计当前会使用的最新非 `superseded` 快照
- 若该快照已过期，拒绝执行

这里不能只检查 `review` 快照，因为 `pre_release` 可能依赖的是 `pre_dev` 快照。

## 前端提示设计

### 风险面板

在 `RiskPanel` 中：

- “最新有效需求快照”区域顶部增加 warning alert
- 当 `latestSnapshot.is_stale = true` 时展示：

`需求已变更，当前快照不是基于最新输入生成，结果可能不可靠，请重新执行评审分析。`

同时：

- “开发前分析”
- “提测前审计”

按钮附近也展示相同 warning，避免用户只看顶部摘要。

### 按钮交互

当快照过期时：

- 按钮仍可见
- 点击 `pre_dev` / `pre_release` 后由后端拦截
- 前端根据错误码展示不同文案

错误文案区分：

- `NO_SNAPSHOT`：`尚未生成有效需求快照，请先执行评审分析。`
- `STALE_SNAPSHOT`：`需求已变更，当前快照已过期，请先重新执行评审分析。`

## 规范化需求文档设计

### 定位

“规范化需求文档”是给人阅读和交付的文档产物，不直接替代有效需求快照。

职责划分：

- `有效需求快照`：服务分析链路
- `规范化需求文档`：服务阅读、评审、下载、外发

两者解耦，但允许复用新鲜快照中的结构化结果。

### 文档数据源

主数据源始终是“当前实时输入”：

- `requirement.raw_text`
- 当前全部 `RequirementInput`

可选复用：

- 若存在且未过期的快照，可复用快照中已经结构化的字段
- 若快照不存在或已过期，导出能力仍然可用

### 无快照时的正文判定

没有快照时，系统没有现成的 `derivation` 标记，因此本期不额外调用 LLM 去补做一轮 derivation 分类。

本期采用更轻量、可预测的规则：

- 直接基于 `requirement.raw_text` 和 `RequirementInput` 生成规范化文档
- 按输入来源和基础规则映射正文前 4 节
- 不做 `explicit / inferred / missing / contradicted` 的二次判定

无快照时的具体生成口径：

- `需求背景与目标`：收原始需求与 `pm_addendum` 中明显属于目标/背景的原文片段
- `主流程`：收原始需求与补充输入中明确描述的流程步骤
- `异常与边界场景`：收明确出现的异常、失败、边界、兜底描述
- `约束与兼容性`：收明确出现的限制、约束、兼容、性能、联动要求
- `待确认事项`：默认写入提示
  - `暂无快照参考，当前文档基于实时输入整理；如需更严格区分已明确与待确认内容，建议先执行评审分析后重新导出。`

也就是说：

- 无快照时，导出能力仍然可用
- 但正文准确性只基于“原文明确表达”，不做 derivation 级别过滤
- 更严格的“只保留 explicit”能力只在存在新鲜快照时生效

### 文档结构

导出 Markdown 固定为：

```md
# 需求标题
## 1. 需求背景与目标
## 2. 主流程
## 3. 异常与边界场景
## 4. 约束与兼容性
## 5. 待确认事项
```

生成规则：

- 正文前 4 节只允许出现“已明确内容”
- 缺失、推断、冲突、待产品确认内容统一放到 `## 5. 待确认事项`
- 不得把推断内容伪装成既定事实

### 明确内容判定

“已明确内容”来源于：

- 原始需求中清晰描述的内容
- `pm_addendum`
- `test_clarification`
- `review_note`
- 未过期快照中 `derivation=explicit` 的字段

不纳入正文的内容：

- `derivation=inferred`
- `derivation=missing`
- `derivation=contradicted`
- 来源冲突但未被正式澄清的内容

这些内容统一转为 `待确认事项` 列表。

补充说明：

- 以上 `derivation` 过滤仅在存在新鲜快照时使用
- 无快照时使用上一节定义的轻量规则，不阻塞导出

### 后端接口

建议新增独立 router，例如：

- `GET /api/requirements/{requirement_id}/normalized-doc/preview`
- `GET /api/requirements/{requirement_id}/normalized-doc/export.md`

`preview` 返回：

```json
{
  "title": "提现流程优化",
  "markdown": "# 提现流程优化\n...",
  "basis_hash": "abc123",
  "uses_fresh_snapshot": true,
  "snapshot_stale": false
}
```

这里选择 `GET` 的原因是：

- 本期 preview 是纯读取和拼装
- 不涉及副作用
- 也不依赖额外请求体参数
- 本期设计中无快照 fallback 不会额外触发 LLM 调用

`export.md` 行为：

- 使用同一套生成逻辑
- 直接返回 Markdown 文件下载

### 生成策略

建议新增服务模块，例如：

- `backend/app/services/normalized_requirement_doc_service.py`

职责：

1. 读取 requirement 和 inputs
2. 复用统一 `compute_basis_hash`
3. 判断最新快照是否可复用
4. 抽取正文 4 节内容
5. 归集待确认事项
6. 输出 Markdown

正文抽取口径：

- `需求背景与目标`：明确背景、目标、业务价值
- `主流程`：明确流程、步骤、状态流转
- `异常与边界场景`：明确异常、边界、兜底
- `约束与兼容性`：明确限制、兼容、性能、联动要求
- `待确认事项`：不确定、冲突、缺失、待补充内容

### 前端交互

建议在需求详情入口附近增加按钮：

- `导出规范化需求`

交互形式：

- 点击后打开 `Modal` 或 `Drawer`
- 展示 Markdown 预览
- 顶部展示说明：
  - `已复用最新快照`
  - 或 `当前快照已过期，本次文档基于实时输入整理`
- 提供 `下载 Markdown` 按钮

前端不需要本地拼 Markdown，统一以后端结果为准。

## 兼容性与边界处理

- 没有快照时，规范化需求文档仍可生成。
- 快照过期时，规范化需求文档仍可生成，但 `uses_fresh_snapshot = false`。
- 若输入极少导致正文为空，前 4 节允许输出“暂无明确内容”，并把可疑项全部写入 `待确认事项`。
- 若 requirement 不存在，接口返回 `404`。

## 推荐下一步

按以下顺序实施：

1. 先补齐 `basis_hash`、统一过期判断和后端错误码
2. 再完成 `RiskPanel` 过期提示
3. 最后补“规范化需求文档预览 + Markdown 下载”

这样可以先把“旧快照误用”的风险堵住，再扩展导出能力。
