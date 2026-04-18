# 需求工作流统一方案

## 一、现状分析

### 三条主线，互不连通

```
主线 A：正统流程
项目与需求 → 规则树 → 用例管理 → 覆盖矩阵 → 回归推荐

主线 B：风险分析（挂在规则树页面）
规则树页面 → RiskPanel（评审/开发前/提测前）→ 有效需求快照 → 风险决策

主线 C：追问分析（完全独立）
追问分析页面 → 自由输入/PDF → LLM 分析 → 结构化结论 → 导出 Markdown
```

### 核心矛盾

| 问题 | 具体表现 |
|------|---------|
| 追问分析是孤岛 | `ClarificationReviewRecord` 没有 `project_id`、没有 `requirement_id`，零关联 |
| 信息手动搬运 | 追问分析产出的缺陷、假设、追问，到规则树那边需要复制粘贴 |
| 风险识别重复劳动 | 追问分析找了一遍缺陷，进规则树后风险识别又从零找一遍，大量重复 |
| 风险分析按钮过多 | 评审前/开发前/提测前/总分析 四个按钮，用户分不清该点哪个 |
| 规则树生成上下文不足 | 只拿 `raw_text` 生成，前面追问分析的结论全部丢失，生成的树只覆盖晴天路径 |

---

## 二、目标流程

```
阶段 1：需求梳理                阶段 2：测试设计               阶段 3：用例覆盖
┌──────────────────┐        ┌──────────────────┐         ┌──────────────────┐
│  追问分析         │        │  规则树生成       │         │  用例管理         │
│  ├ 自由输入/PDF   │   →    │  （自动带入前序   │    →    │  覆盖矩阵         │
│  ├ LLM 找缺陷     │        │    结论作为上下文）│         │  回归推荐         │
│  ├ 跟进标记状态   │        │  风险分析（增量） │         │                  │
│  └ 一键创建需求   │        │  （1次调用,分层） │         │                  │
└──────────────────┘        └──────────────────┘         └──────────────────┘
         ↓ 数据自动流转 ↓              ↓ 数据自动流转 ↓
   RequirementInput 沉淀        RiskItem + 规则树节点
```

### 关键设计决策

1. **追问分析是需求的上游，不是下游** — 不是追问分析关联已有需求，而是追问分析产出生成需求
2. **追问分析结论可跟进** — 每条产出有处理状态（待确认/已确认/按假设推进/不再追问），包括角色追问问题
3. **风险分析从 4 个按钮砍为 1 个** — 1 次 LLM 调用，根据已有 input 自动判断分析深度，结果按视角分层展示
4. **风险分析做增量** — 继承追问分析已有结论，不重复发现；有新 input 进来后可重新分析
5. **规则树生成自动带入全部上下文** — 读取 RequirementInput + RiskItem 组装进 prompt
6. **保留独立追问分析入口** — 不关联需求的一次性使用场景仍然可用

---

## 三、分阶段实施

### Phase 1：追问分析结论可跟进（前端为主）

> 目标：追问分析从"用完即弃"变成"持续跟进的工作台"

#### 数据变更

`ClarificationReviewRecord.result_json` 中每条 item 增加跟进字段。
适用于三类条目：`known_requirement_gaps`、`assumption_items`、`priority_questions_by_role` 中的问题条目。

```json
{
  "known_requirement_gaps": [
    {
      "gap": "驳回后通知处理规则缺失",
      "gap_type": "rule_missing",
      "reason": "...",
      "impact": "...",
      "priority": "P0",
      "blocking_reason": "...",
      "resolution_status": "confirmed",
      "resolution_note": "产品确认：驳回后撤回已发通知",
      "resolved_by": "张三",
      "resolved_at": "2026-04-15T10:00:00Z"
    }
  ],
  "assumption_items": [
    {
      "assumption": "沿用老系统通知机制",
      "basis": "...",
      "risk": "...",
      "resolution_status": "assume_and_proceed",
      "resolution_note": "找不到运营确认，先按假设推进"
    }
  ],
  "priority_questions_by_role": {
    "产品": [
      {
        "question": "审批超时后是否自动通过？",
        "why_ask": "...",
        "risk_if_unasked": "...",
        "resolution_status": "confirmed",
        "resolution_note": "产品确认：超时自动驳回，不是自动通过",
        "resolved_by": "李四",
        "resolved_at": "2026-04-15T14:00:00Z"
      }
    ]
  }
}
```

`resolution_status` 枚举：

| 值 | 含义 | 对下游的影响 |
|---|------|------------|
| `pending` | 待确认（默认） | 创建需求时作为待确认项挂着 |
| `confirmed` | 已确认 | 作为确定输入沉淀到需求正文 |
| `assume_and_proceed` | 按假设推进 | 沉淀到需求正文 + 自动生成 RiskItem |
| `dismissed` | 不再追问 | 跳过，不沉淀 |

#### 前端改动

- `ClarificationReview/index.tsx` — 结果展示区每条 gap/assumption/question 旁加状态下拉 + 备注输入
- 新增 API：`PATCH /api/ai/clarification-review/records/{id}/items` — 批量更新 item 的 resolution 状态

#### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/schemas/clarification_review.py` | 新增 resolution 相关字段 |
| `backend/app/api/clarification_review.py` | 新增 PATCH 端点 |
| `backend/app/services/clarification_review_service.py` | 新增 update_item_resolutions 函数 |
| `frontend/src/types/index.ts` | item 类型加 resolution 字段 |
| `frontend/src/api/clarificationReview.ts` | 新增 updateItemResolutions API |
| `frontend/src/pages/ClarificationReview/index.tsx` | 状态下拉 + 备注 UI |

---

### Phase 2：追问分析 → 一键创建需求

> 目标：追问分析的产出能自动生成一条需求记录，结论同步沉淀为 RequirementInput

#### 数据变更

`ClarificationReviewRecord` 新增列：

```python
generated_requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=True)
```

`RequirementInput.input_type` 新增枚举值：

```python
class InputType(str, enum.Enum):
    raw_requirement = "raw_requirement"
    pm_addendum = "pm_addendum"
    test_clarification = "test_clarification"
    review_note = "review_note"
    clarification_confirmed = "clarification_confirmed"      # 追问分析已确认结论
    clarification_assumption = "clarification_assumption"    # 追问分析按假设推进
    clarification_pending = "clarification_pending"          # 追问分析待确认项
```

#### 创建需求的逻辑

```
用户点击"创建需求" →

1. 组装 raw_text：
   - 追问分析的 5 个输入字段拼接
   - 已确认的澄清结论追加到对应段落
   - 按假设推进的标注为假设

2. 创建 Requirement 记录（需选择 project_id）

3. 自动创建 RequirementInput 记录：
   - resolution_status=confirmed → type=clarification_confirmed
   - resolution_status=assume_and_proceed → type=clarification_assumption
   - resolution_status=pending → type=clarification_pending

4. 回写 generated_requirement_id 到 ClarificationReviewRecord
```

#### UX 补充

创建需求成功后弹确认弹窗，提供两个入口：
- "去规则树页面" — 跳转到新需求的规则树页面，直接开始测试设计
- "留在当前页面" — 继续跟进未处理完的待确认项

#### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/models/entities.py` | ClarificationReviewRecord 加列 + InputType 加枚举 |
| `backend/app/core/schema_migrations.py` | 新增迁移 |
| `backend/app/services/clarification_review_service.py` | 新增 create_requirement_from_review 函数 |
| `backend/app/api/clarification_review.py` | 新增 POST /records/{id}/create-requirement |
| `frontend/src/pages/ClarificationReview/index.tsx` | "创建需求"按钮 + 选择项目弹窗 + 创建成功跳转弹窗 |

---

### Phase 3：风险分析合并为 1 次调用

> 目标：4 个按钮 → 1 个按钮，1 次 LLM 调用，结果按视角分层

#### 当前状态

```
评审前分析（review）    → 独立 LLM 调用 → RiskItem (stage=review)
开发前分析（pre_dev）   → 独立 LLM 调用 → RiskItem (stage=pre_dev)
提测前分析（pre_release）→ 独立 LLM 调用 → RiskItem (stage=pre_release)
总分析                  → 依次调用上面三个
```

#### 改为

```
风险分析（1个按钮，1次调用）→ LLM 输出自带分类 → RiskItem 按 stage 标签存储
```

#### 阶段性深度的保留

1 个按钮但不丢失阶段性分析能力：
- 后端跑分析前先查 `RequirementInput`，把已有的按类型分组
- Prompt 中告诉 LLM 当前可用的信息类型，LLM 自动判断能分析到什么深度
- 如果后续有新 input 沉淀进来（如技术设计、测试反馈），用户可重新点"风险分析"，LLM 增量识别新风险
- 未来如果新增 `input_type=tech_design` 等类型，分析深度自动提升，无需改代码

#### Prompt 改造

```
请基于当前可用的信息，从以下视角分析需求风险：

1. 需求层（评审阶段）：需求是否完整、清晰、无矛盾
2. 设计层（开发前）：技术方案是否有遗漏、数据流是否完整
3. 验收层（提测前）：测试是否能覆盖所有分支、是否有阻塞项

## 当前可用信息

### 需求原文
{raw_text}

### 追问分析已识别的问题（请勿重复，仅做增量分析）
{从 RequirementInput 取 type=clarification_* 的}

### 其他已有输入
{按 input_type 分组列出}

注意：根据当前已有信息的丰富程度，判断每个视角能分析到什么深度。
如果缺少技术设计信息，设计层分析可以偏保守，指出"待技术方案补充后可深入"。
请输出时标注每条风险属于哪个视角。
```

#### 前端改动

- RiskPanel 区域：去掉 4 个按钮，改为 1 个"风险分析"按钮
- 结果展示：按需求层/设计层/验收层折叠分组

#### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/services/risk_analysis_service.py` | 合并分析逻辑，prompt 改造 |
| `backend/app/services/prompts/` | 合并 3 套 prompt 为 1 套 |
| `backend/app/api/risk_analysis.py` | 简化端点 |
| `frontend/src/pages/RuleTree/RiskPanel.tsx` | UI 简化 |

---

### Phase 4：规则树生成自动带入全部上下文

> 目标：规则树生成时自动读取前序结论，生成的树覆盖异常分支和风险假设

#### 改动点

规则树生成 service 的 prompt 组装逻辑，从：

```
请根据以下需求生成决策树：
{raw_text}
```

改为：

```
请根据以下需求及补充信息生成决策树：

## 需求原文
{raw_text}

## 已确认的需求澄清（必须体现在规则树中）
{RequirementInput where type=clarification_confirmed}

## 风险假设（需要生成对应的异常/边界分支节点）
{RequirementInput where type=clarification_assumption}

## 待确认项（如果影响流程分支，标记为待确认节点）
{RequirementInput where type=clarification_pending}

## 风险分析结论（关注异常路径覆盖）
{RiskItem where requirement_id=当前需求}

注意：
- 已确认的澄清必须体现在规则树中
- 风险假设需生成对应的异常/边界分支节点
- 已识别的缺陷如果影响流程分支，标记为待确认节点
```

#### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/services/rule_tree_service.py` | prompt 组装逻辑，多查 RequirementInput + RiskItem |
| `backend/app/services/prompts/rule_tree_prompts.py` | prompt 模板更新 |

---

### Phase 5：需求工作台（远期）

> 目标：提供一个统一视图，让用户看到一个需求从梳理到测试的完整生命周期

Phase 1-4 做的是数据层打通，不动页面结构。Phase 5 在数据全部打通、用户实际使用后，再决定页面组织方式。

#### 两个候选方案

| 方案 | 描述 | 优势 | 劣势 |
|------|------|------|------|
| A：新建"需求工作台"页面 | Tab 切换（追问分析 / 需求详情 / 规则树 / 风险 / 用例） | 完整的生命周期视图 | 改动大，与现有页面功能重叠 |
| B：现有规则树页面加阶段导航 | 顶部加导航条，能跳回追问分析记录和需求详情 | 改动小，渐进式 | 视觉上不够统一 |

#### 决策时机

等 Phase 1-4 完成、用户实际跑通整条链路后，根据使用反馈决定。不提前做。

---

## 四、完整数据流

```
追问分析页面
│  输入：自由文本 / PDF
│  产出：inferred_items, assumption_items, known_requirement_gaps, questions
│
├─ 用户跟进标记 resolution_status（Phase 1）
│  ├─ gaps / assumptions / questions 均可标记
│  └─ 四种状态：pending / confirmed / assume_and_proceed / dismissed
│
├─ 一键创建需求（Phase 2）
│  ├─ 生成 Requirement (raw_text = 组装后的完整需求)
│  ├─ 生成 RequirementInput × N (type = clarification_confirmed / assumption / pending)
│  ├─ 回写 generated_requirement_id
│  └─ 弹窗提供跳转入口（去规则树 / 留在当前页面）
│
│  ┌─────────────────────────────────────────┐
│  │  需求记录 (Requirement)                  │
│  │  ├─ RequirementInput (追问分析沉淀)      │
│  │  ├─ EffectiveRequirementSnapshot (快照)  │
│  │  └─ ... 后续输入可继续追加               │
│  └─────────────────────────────────────────┘
│
├─ 风险分析 1 次调用（Phase 3）
│  ├─ 读取 RequirementInput 作为已知上下文（去重，不重复发现）
│  ├─ 根据已有 input 类型自动判断分析深度
│  ├─ LLM 增量分析
│  ├─ 产出 RiskItem × N (按 stage 分层)
│  └─ 有新 input 进来后可重新分析
│
├─ 规则树生成（Phase 4）
│  ├─ 读取 RequirementInput + RiskItem
│  ├─ 组装增强 prompt
│  └─ 生成的树自动覆盖异常分支和风险假设
│
└─ 用例管理 / 覆盖矩阵 / 回归推荐（已有，无需改动）
```

---

## 五、实施优先级与依赖

```
Phase 1（追问结论可跟进）    ← 无依赖，可立即开始
    ↓
Phase 2（一键创建需求）      ← 依赖 Phase 1（需要 resolution_status）
    ↓
Phase 3（风险分析合并）      ← 依赖 Phase 2（需要 RequirementInput 数据）
Phase 4（规则树上下文增强）   ← 依赖 Phase 2（需要 RequirementInput 数据）
                              Phase 3 和 4 互不依赖，可并行
    ↓
Phase 5（需求工作台）         ← 依赖 Phase 1-4 全部完成 + 用户使用反馈
```

### 工作量估算

| 阶段 | 后端 | 前端 | 说明 |
|------|------|------|------|
| Phase 1 | 小 | 中 | 主要是前端 UI，后端只加一个 PATCH 端点 |
| Phase 2 | 中 | 中 | 核心逻辑在 service 层组装 raw_text 和创建 RequirementInput |
| Phase 3 | 中 | 小 | 主要是 prompt 改造和 service 层合并，前端只是去按钮 |
| Phase 4 | 小 | 无 | 只改 prompt 组装逻辑，纯后端 |
| Phase 5 | 小 | 大 | 主要是前端页面重组，后端几乎不动 |

---

## 六、不变的部分

- 独立的追问分析入口保留，不关联需求的一次性场景仍可用
- 项目与需求页面的基本 CRUD 不变
- 用例管理、覆盖矩阵、回归推荐不动
- 产品知识库保持独立
- 不强制使用顺序，每个阶段都可以跳过
