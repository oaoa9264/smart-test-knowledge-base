# 智能测试结构平台 — 项目知识库

> 本文档是项目的完整知识库，覆盖项目概述、技术架构、数据模型、API 接口、前端页面、核心业务逻辑、开发规范等，供团队成员快速上手与日常参考。

---

## 1. 项目概述

### 1.1 项目名称

**智能测试结构平台 (Smart Test Structure Platform)**

### 1.2 项目目标

构建一个将「需求 → 规则树 → 测试用例 → 覆盖矩阵」全链路打通的测试知识管理平台，帮助 QA 团队：

- 可视化管理业务规则，以树状结构拆解需求
- 将测试用例与规则节点/路径精确绑定
- 自动计算覆盖率矩阵，快速定位高风险未覆盖区域
- 规则变更时自动标记受影响用例，降低回归遗漏风险
- 通过 AI 半自动解析需求文本，快速生成规则草稿

### 1.3 功能优先级

| 优先级 | 功能模块 | 说明 |
|--------|----------|------|
| **P0** | 规则树可视化 CRUD | 创建/编辑/删除规则节点，树状结构可视化展示 |
| **P0** | 用例管理与规则绑定 | 测试用例的增删改查，支持绑定到规则节点和规则路径 |
| **P0** | 覆盖矩阵 | 自动计算节点/路径覆盖率，高风险未覆盖告警 |
| **P1** | AI 半自动解析草稿导入 | 输入 PRD 文本，AI 解析为规则草稿节点，人工确认后导入 |
| **P1** | 规则变更影响分析 | 规则节点修改/删除后自动标记关联用例为 `needs_review` |
| **P1** | 回归推荐算法层 | 基于带权集合覆盖的贪心算法，输出最小回归用例集（FULL/CHANGE）及可解释收益 |
| **P1+** | 需求拆解 | 支持仅流程图、仅文字或图文联合分析，生成判断树并可一键导入 |
| **P1+** | 需求版本化 | 需求支持创建新版本、版本列表查看，规则树按版本隔离 |
| **P1+** | 规则树版本 Diff | LLM 语义级对比两个版本的规则树差异，含算法兜底 |
| **P1+** | 规则树会话式 AI 生成 | 基于会话的规则树生成、审查、确认导入、增量更新 |
| **P1+** | 风险识别分析 | AI 风险识别分析、风险决策、风险转节点、删除风险项 |
| **P1+** | 测试方案与用例生成 | AI 基于规则树生成测试方案 → 生成测试用例 → 确认导入用例库 |

### 1.4 核心业务流

```
创建项目 → 创建需求 → 构建规则树 → 创建测试用例(绑定规则节点)
                          ↓                        ↓
                    AI 解析辅助              覆盖矩阵自动计算
                          ↓                        ↓
                    规则变更 → 影响分析 → 标记 needs_review
                          ↓
                 回归推荐 (FULL/CHANGE) → 输出最小回归集 + 解释

                    ┌────────────────────────────────────────┐
                    │      需求拆解 (P1+ 新增)          │
                    │ 上传流程图和/或描述 → AI 分析 → 生成判断树 │
                    │ → 人工确认 → 一键导入正式库               │
                    └────────────────────────────────────────┘

                    ┌────────────────────────────────────────┐
                    │      需求版本化 + 规则树 Diff (P1+ 新增)  │
                    │ 创建新版本 → 独立编辑规则树 → 版本对比      │
                    │ (LLM 语义 Diff + 算法兜底)               │
                    └────────────────────────────────────────┘

                    ┌────────────────────────────────────────┐
                    │      规则树会话式 AI 生成 (P1+ 新增)      │
                    │ 创建会话 → AI 生成 → AI 审查 → 确认导入    │
                    │ → 需求更新后增量更新规则树                 │
                    └────────────────────────────────────────┘

                    ┌────────────────────────────────────────┐
                    │      风险识别分析 (P1+ 新增)              │
                    │ AI 识别规则树风险 → 逐条决策 → 转为节点     │
                    └────────────────────────────────────────┘

                    ┌────────────────────────────────────────┐
                    │      测试方案与用例生成 (P1+ 新增)        │
                    │ 规则树 → AI 生成测试方案 → AI 生成用例    │
                    │ → 人工审查编辑 → 确认导入用例库            │
                    └────────────────────────────────────────┘
```

---

## 2. 技术架构

### 2.1 整体架构

采用**前后端分离的单体仓库 (Monorepo)** 架构，三个核心服务通过 Docker Compose 编排：

```
┌─────────────┐     HTTP/REST     ┌─────────────┐     SQL      ┌────────────┐
│   Frontend  │  ◄──────────────► │   Backend   │ ◄──────────► │ PostgreSQL │
│  React+Vite │    localhost:8000  │   FastAPI   │              │   (或 SQLite) │
│  :5173      │                   │  :8000      │              │  :5432     │
└─────────────┘                   └─────────────┘              └────────────┘
```

### 2.2 技术栈详情

#### 后端 (Backend)

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 运行时 |
| FastAPI | 0.103.2 | Web 框架，自动生成 OpenAPI 文档 |
| SQLAlchemy | 2.0.36 | ORM，数据模型定义与数据库操作 |
| Pydantic | 1.9.0 | 数据校验与序列化 (请求/响应 DTO) |
| Uvicorn | 0.22.0 | ASGI 服务器 |
| psycopg | 3.2.9 | PostgreSQL 驱动 |
| python-multipart | 0.0.8 | 文件上传 (multipart/form-data) 支持 |
| openpyxl | 3.1.5 | Excel 用例文件解析 (`.xlsx/.xlsm`) |
| xmindparser | 1.0.9 | XMind 用例文件解析 (`.xmind`) |
| Pytest | 7.4.4 | 单元测试 & 接口测试 |
| httpx | 0.24.1 | HTTP 客户端（测试 + OpenAI/智谱 SSE 调用） |
| openai | 1.51.2 | OpenAI SDK（支持 `OPENAI_BASE_URL` 网关接入） |

#### 前端 (Frontend)

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.3.1 | UI 框架 |
| TypeScript | 5.8.2 | 类型安全 |
| Vite | 2.9.18 | 构建工具 & 开发服务器 |
| Ant Design | 5.27.0 | UI 组件库 |
| @ant-design/icons | 5.6.1 | Ant Design 图标库 |
| simple-mind-map | 0.14.0-fix.1 | 规则树/判断树思维导图可视化（拖拽改层级、适应画布、导出 PNG/SVG/XMind） |
| Zustand | 5.0.8 | 轻量级状态管理 |
| Axios | 1.8.4 | HTTP 请求客户端 |
| React Router | 6.30.1 | 客户端路由 |
| react-markdown | 8.0.7 | Markdown 渲染 (测试方案展示) |

#### 基础设施

| 技术 | 用途 |
|------|------|
| Docker Compose | 容器编排 (postgres + backend + frontend) |
| PostgreSQL 15 | 生产数据库 |
| SQLite | 本地开发/测试数据库 (零配置) |

### 2.3 目录结构

```
.
├── backend/
│   ├── app/
│   │   ├── api/                    # API 路由层
│   │   │   ├── ai_parse.py         # AI 解析接口
│   │   │   ├── architecture.py     # 需求拆解接口 (P1+ 新增)
│   │   │   ├── coverage.py         # 覆盖矩阵接口
│   │   │   ├── projects.py         # 项目 & 需求接口
│   │   │   ├── recommendation.py   # 回归推荐接口 (P1 新增)
│   │   │   ├── risks.py            # 风险识别分析接口 (P1+ 新增)
│   │   │   ├── rule_tree_session.py # 规则树会话式 AI 生成接口 (P1+ 新增)
│   │   │   ├── rules.py            # 规则树 CRUD & 影响分析接口
│   │   │   ├── test_plan.py        # 测试方案与用例生成接口 (P1+ 新增)
│   │   │   ├── testcase_import.py  # 测试用例智能导入接口 (P1 新增)
│   │   │   ├── testcases.py        # 测试用例接口
│   │   │   └── tree_diff.py        # 规则树版本 Diff 接口 (P1+ 新增)
│   │   ├── core/
│   │   │   ├── database.py         # 数据库连接 & Session 管理
│   │   │   └── schema_migrations.py # 数据库迁移辅助 (需求版本化字段)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── entities.py         # SQLAlchemy 实体模型
│   │   ├── schemas/
│   │   │   ├── __init__.py         # Schema 统一导出
│   │   │   ├── architecture.py     # 需求拆解 Pydantic DTO (P1+ 新增)
│   │   │   ├── project.py          # 项目/需求 Pydantic DTO (含 Create/Update/Read)
│   │   │   ├── recommendation.py   # 回归推荐 DTO (P1 新增)
│   │   │   ├── risk.py             # 风险分析 DTO (P1+ 新增)
│   │   │   ├── rule.py             # 规则节点/路径 Pydantic DTO
│   │   │   ├── rule_tree_session.py # 规则树会话 DTO (P1+ 新增)
│   │   │   ├── test_plan.py        # 测试方案与用例生成 DTO (P1+ 新增)
│   │   │   ├── testcase.py         # 测试用例 Pydantic DTO (含 Create/Update/Read/UpdateStatus)
│   │   │   ├── testcase_import.py  # 测试用例导入 DTO (解析预览/确认导入)
│   │   │   └── tree_diff.py        # 规则树版本 Diff DTO (P1+ 新增)
│   │   ├── services/
│   │   │   ├── ai_parser.py        # AI 需求解析逻辑
│   │   │   ├── architecture_analyzer.py  # 需求拆解分析引擎 (P1+ 新增)
│   │   │   ├── base_llm_client.py  # LLM 共享基类（SSE/重试/JSON 解析）
│   │   │   ├── cover_set.py        # 用例覆盖集合计算 (P1 新增)
│   │   │   ├── coverage.py         # 覆盖率矩阵计算
│   │   │   ├── fallback_llm_client.py # LLM 顺序回退编排器（OpenAI -> 智谱）
│   │   │   ├── impact.py           # 变更影响分析
│   │   │   ├── impact_domain.py    # 变更影响域计算 (P1 新增)
│   │   │   ├── llm_client.py       # 向后兼容包装器（自动构建多模型回退链）
│   │   │   ├── openai_client.py    # OpenAI 客户端实现（json_object）
│   │   │   ├── prompts/            # Prompt 模板（需求拆解 + 测试用例匹配 + 规则树会话 + 测试方案生成）
│   │   │   ├── recommender.py      # 贪心推荐算法 (P1 新增)
│   │   │   ├── risk_scorer.py      # 节点风险权重计算 (P1 新增)
│   │   │   ├── risk_service.py     # 风险分析服务 (P1+ 新增)
│   │   │   ├── rule_tree_session.py # 规则树会话服务 (P1+ 新增)
│   │   │   ├── test_plan_generator.py # 测试方案与用例生成服务 (P1+ 新增)
│   │   │   ├── tree_diff.py        # 规则树版本 Diff 服务 (P1+ 新增)
│   │   │   ├── testcase_importer.py # Excel/XMind 用例解析服务
│   │   │   ├── testcase_matcher.py  # 用例-规则节点匹配服务（LLM + 关键词兜底）
│   │   │   ├── rule_engine.py      # 规则路径推导 (DFS)
│   │   │   └── zhipu_client.py     # 智谱客户端实现（含 thinking 参数）
│   │   └── main.py                 # FastAPI 应用入口
│   ├── tests/
│   │   ├── conftest.py             # 测试配置（自动重建数据库，保障用例隔离）
│   │   ├── test_ai_parser.py       # AI 解析（LLM 优先 + 兜底）单测
│   │   ├── test_api_smoke.py       # API 冒烟测试
│   │   ├── test_architecture_analyzer.py  # 需求拆解分析单测 (P1+ 新增)
│   │   ├── test_coverage_and_impact.py    # 覆盖率 & 影响分析单测
│   │   ├── test_fallback_llm.py    # 多模型回退链路测试
│   │   ├── test_llm_client.py      # LLM 包装器组链与委托行为测试
│   │   ├── test_openai_client.py   # OpenAI 客户端请求格式与 JSON 解析测试
│   │   ├── test_projects_crud_api.py      # 项目 & 需求 CRUD API 测试
│   │   ├── test_recommender.py     # 推荐算法 & 推荐 API 测试 (P1 新增)
│   │   ├── test_risk_service.py    # 风险分析并发合并/覆盖写入回归测试 (P1+ 新增)
│   │   ├── test_rule_engine.py     # 规则引擎单测
│   │   ├── test_testcase_import_api.py      # 测试用例导入 API 测试
│   │   ├── test_testcase_import_services.py # 测试用例导入服务测试
│   │   └── test_testcases_api.py   # 测试用例 CRUD & 需求筛选 API 测试
│   ├── uploads/                    # 上传文件目录 (运行时生成)
│   │   └── architecture/           # 架构流程图存储
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/                    # API 调用封装
│   │   │   ├── architecture.ts     # 需求拆解 API (P1+ 新增)
│   │   │   ├── client.ts           # Axios 实例 (baseURL 配置 + getErrorMessage)
│   │   │   ├── coverage.ts         # 覆盖矩阵 API
│   │   │   ├── projects.ts         # 项目 & 需求 & 版本化 API
│   │   │   ├── recommendation.ts   # 回归推荐 API (P1 新增)
│   │   │   ├── risks.ts            # 风险分析 API (P1+ 新增)
│   │   │   ├── rules.ts            # 规则树 & AI 解析 API
│   │   │   ├── ruleTreeSession.ts  # 规则树会话 API (P1+ 新增)
│   │   │   ├── testcases.ts        # 测试用例 API
│   │   │   ├── testPlan.ts         # 测试方案与用例生成 API (P1+ 新增)
│   │   │   └── treeDiff.ts         # 规则树版本 Diff API (P1+ 新增)
│   │   ├── pages/
│   │   │   ├── ArchitectureAnalysis/  # 需求拆解页 (P1+ 新增)
│   │   │   ├── ProjectList/        # 项目 & 需求管理页
│   │   │   ├── Recommendation/     # 回归推荐页 (P1 新增)
│   │   │   ├── RuleTree/           # 规则树可视化编辑页（simple-mind-map）
│   │   │   │   ├── MindMapWrapper.tsx  # simple-mind-map React 封装
│   │   │   │   ├── dataAdapter.ts      # RuleNode[] <-> MindMapTree 双向转换 + 风险高亮
│   │   │   │   ├── mindMapTheme.ts     # 规则树主题注册
│   │   │   │   ├── RiskPanel.tsx       # 风险识别面板 (P1+ 新增)
│   │   │   │   └── index.tsx           # 规则树页面（目录树 + 思维导图 + 版本管理 + 会话 AI + 风险面板）
│   │   │   ├── TestCases/          # 测试用例管理页
│   │   │   └── Coverage/           # 覆盖矩阵页
│   │   ├── stores/
│   │   │   └── appStore.ts         # 全局状态 (Zustand)
│   │   ├── types/
│   │   │   ├── index.ts            # TypeScript 类型定义
│   │   │   └── simple-mind-map-full.d.ts # simple-mind-map/full 类型声明
│   │   ├── utils/
│   │   │   └── enumLabels.ts       # 枚举值中文标签映射 & 获取函数
│   │   ├── App.tsx                 # 应用主框架 (路由 & 布局)
│   │   ├── main.tsx                # 入口文件
│   │   └── styles.css              # 全局样式
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── docs/plans/                     # 实现计划文档
├── docker-compose.yml              # 容器编排
└── README.md
```

---

## 3. 数据模型

### 3.1 实体关系图 (ER)

```
┌──────────┐ 1    N ┌──────────────┐ 1    N ┌──────────────┐
│ Project  │───────►│ Requirement  │───────►│  RuleNode    │
└──────┬───┘        └──────┬───────┘        └──────┬───────┘
  │ 1  │ 1            │ 1  │ 1                     │ M
  │    │              │    │                        │
  │ N  │ N            │ N  │ N                 ┌────┴────┐
┌─▼────┴─┐     ┌─────▼──┐ ▼──────────┐        │ assoc   │
│TestCase│◄───►│RulePath│ │Architec-  │        │ tables  │
└────────┘ M:N └────────┘ │tureAnaly- │        └─────────┘
                          │sis        │
                          └───────────┘

Requirement 1 ─── N RecoRun 1 ─── N RecoResult N ─── 1 TestCase
Requirement 1 ─── N TestPlanSession

Project 1 ─── N DiffRecord (base_requirement_id / compare_requirement_id → Requirement)
```

### 3.2 实体详细定义

#### Project (项目)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 项目 ID |
| name | String(120) | NOT NULL, UNIQUE | 项目名称 |
| description | Text | 可选 | 项目描述 |
| created_at | DateTime | NOT NULL, 默认 UTC now | 创建时间 |

#### Requirement (需求)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 需求 ID |
| project_id | Integer | FK → projects.id, NOT NULL | 所属项目 |
| title | String(255) | NOT NULL | 需求标题 |
| raw_text | Text | NOT NULL | 需求原文 |
| source_type | Enum(prd/flowchart/api_doc) | NOT NULL, 默认 prd | 来源类型 |
| version | Integer | NOT NULL, 默认 1 | 版本号 |
| requirement_group_id | Integer | 可选, 索引 | 版本组 ID (首次创建版本时设为 v1 的 id) |
| created_at | DateTime | NOT NULL | 创建时间 |

#### RuleNode (规则节点)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(64) | PK (UUID) | 节点 ID |
| requirement_id | Integer | FK → requirements.id, NOT NULL | 所属需求 |
| parent_id | String(64) | FK → rule_nodes.id, 可选 | 父节点 (自引用) |
| node_type | Enum | NOT NULL | 节点类型 |
| content | Text | NOT NULL | 节点内容描述 |
| risk_level | Enum | NOT NULL, 默认 medium | 风险等级 |
| version | Integer | NOT NULL, 默认 1 | 版本号 (每次修改 +1) |
| status | Enum | NOT NULL, 默认 active | 节点状态 |

**节点类型 (NodeType):**
- `root` — 根节点
- `condition` — 条件节点
- `branch` — 分支节点
- `action` — 动作节点
- `exception` — 异常节点

**风险等级 (RiskLevel):**
- `critical` — 严重
- `high` — 高
- `medium` — 中
- `low` — 低

**节点状态 (NodeStatus):**
- `active` — 活跃
- `modified` — 已修改
- `deleted` — 已删除 (软删除)

#### RulePath (规则路径)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(64) | PK (UUID) | 路径 ID |
| requirement_id | Integer | FK → requirements.id, NOT NULL | 所属需求 |
| node_sequence | Text | NOT NULL | 逗号分隔的节点 ID 序列 |

规则路径是自动派生的，表示规则树中从根到叶的每条完整路径。每当规则节点发生增删改时，系统会自动重新计算所有路径。

#### TestCase (测试用例)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 用例 ID |
| project_id | Integer | FK → projects.id, NOT NULL | 所属项目 |
| title | String(255) | NOT NULL | 用例标题 |
| precondition | Text | 可选, 默认空字符串 | 前置条件 |
| steps | Text | NOT NULL | 执行步骤 |
| expected_result | Text | NOT NULL | 预期结果 |
| risk_level | Enum | NOT NULL, 默认 medium | 风险等级 |
| status | Enum | NOT NULL, 默认 active | 用例状态 |
| created_at | DateTime | NOT NULL | 创建时间 |

**用例状态 (TestCaseStatus):**
- `active` — 有效
- `needs_review` — 需要复查 (规则变更触发)
- `invalidated` — 已失效

#### ArchitectureAnalysis (需求拆解分析记录，P1+ 新增)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 分析记录 ID |
| project_id | Integer | FK → projects.id, NOT NULL | 所属项目 |
| requirement_id | Integer | FK → requirements.id, 可选 | 关联需求 (导入时自动创建或绑定) |
| title | String(255) | NOT NULL | 需求标题 |
| image_path | Text | 可选 | 上传的流程图文件路径 |
| description_text | Text | 可选 | 文字描述 |
| analysis_result | Text | 可选 | JSON 序列化的分析结果 (含判断树/测试方案/风险点/用例) |
| status | Enum | NOT NULL, 默认 pending | 分析状态 |
| created_at | DateTime | NOT NULL, 默认 UTC now | 创建时间 |

**分析状态 (AnalysisStatus):**
- `pending` — 待处理
- `completed` — 已完成分析
- `imported` — 已导入正式库

#### RecoRun (回归推荐运行记录，P1 新增)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 推荐运行 ID |
| requirement_id | Integer | FK → requirements.id, NOT NULL | 所属需求 |
| mode | Enum(FULL/CHANGE) | NOT NULL, 默认 FULL | 推荐模式 |
| k | Integer | NOT NULL | 回归K上限 |
| input_changed_node_ids | Text | 可选 | CHANGE 模式输入节点 ID 列表 (JSON 序列化) |
| total_target_risk | Float | NOT NULL, 默认 0 | 目标风险总值 |
| covered_risk | Float | NOT NULL, 默认 0 | 已覆盖风险值 |
| coverage_ratio | Float | NOT NULL, 默认 0 | 风险覆盖率 |
| created_at | DateTime | NOT NULL, 默认 UTC now | 创建时间 |

**推荐模式 (RecoMode):**
- `FULL` — 全量回归
- `CHANGE` — 变更回归

#### RecoResult (回归推荐结果明细，P1 新增)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 结果明细 ID |
| run_id | Integer | FK → reco_run.id, NOT NULL | 所属推荐运行 |
| rank | Integer | NOT NULL | 推荐顺位 |
| case_id | Integer | FK → test_cases.id, NOT NULL, ON DELETE CASCADE | 推荐用例 ID |
| gain_risk | Float | NOT NULL, 默认 0 | 本轮新增风险收益 |
| gain_node_ids | Text | NOT NULL | 本轮新增覆盖节点 ID 列表 (JSON 序列化) |
| top_contributors | Text | NOT NULL | 关键贡献节点及风险值 (JSON 序列化) |
| why_selected | String(255) | NOT NULL | 可解释推荐原因 |

#### RuleTreeSession (规则树会话，P1+ 新增)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 会话 ID |
| requirement_id | Integer | FK → requirements.id, NOT NULL, 索引 | 所属需求 |
| title | String(255) | NOT NULL | 会话标题 |
| status | Enum | NOT NULL, 默认 active | 会话状态 |
| confirmed_tree_snapshot | Text | 可选 | 确认后的规则树 JSON 快照 |
| requirement_text_snapshot | Text | 可选 | 需求文本快照 |
| created_at | DateTime | NOT NULL | 创建时间 |
| updated_at | DateTime | NOT NULL | 更新时间 |

**会话状态 (RuleTreeSessionStatus):**
- `active` — 进行中
- `confirmed` — 已确认并导入
- `archived` — 已归档

#### RuleTreeMessage (规则树会话消息，P1+ 新增)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 消息 ID |
| session_id | Integer | FK → rule_tree_sessions.id, NOT NULL, 索引 | 所属会话 |
| role | String(20) | NOT NULL | 角色 (user/assistant/system) |
| content | Text | NOT NULL | 消息内容 |
| message_type | String(50) | NOT NULL | 消息类型 (user_input/generation/review/update/confirm 等) |
| tree_snapshot | Text | 可选 | 该消息关联的规则树 JSON 快照 |
| created_at | DateTime | NOT NULL | 创建时间 |

#### TestPlanSession (测试方案会话，P1+ 新增)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 会话 ID |
| requirement_id | Integer | FK → requirements.id, NOT NULL, 索引 | 所属需求 |
| status | Enum | NOT NULL, 默认 plan_generating | 会话状态 |
| plan_markdown | Text | 可选 | 生成的测试方案 Markdown 文本 |
| test_points_json | Text | 可选 | 测试点列表 JSON 序列化 |
| generated_cases_json | Text | 可选 | 生成的测试用例列表 JSON 序列化 |
| confirmed_case_ids_json | Text | 可选 | 确认导入后的用例 ID 列表 JSON 序列化 |
| created_at | DateTime | NOT NULL | 创建时间 |
| updated_at | DateTime | NOT NULL | 更新时间 |

**会话状态 (TestPlanSessionStatus):**
- `plan_generating` — 正在生成测试方案
- `plan_generated` — 测试方案已生成
- `cases_generating` — 正在生成测试用例
- `cases_generated` — 测试用例已生成
- `confirmed` — 已确认导入
- `archived` — 已归档

#### DiffRecord (版本对比记录，P1+ 新增)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 记录 ID |
| project_id | Integer | FK → projects.id, NOT NULL, 索引 | 所属项目 |
| base_requirement_id | Integer | FK → requirements.id, NOT NULL | 基准需求版本 |
| compare_requirement_id | Integer | FK → requirements.id, NOT NULL | 对比需求版本 |
| base_version | Integer | NOT NULL | 基准版本号 |
| compare_version | Integer | NOT NULL | 对比版本号 |
| result_json | Text | NOT NULL | 对比结果 JSON（SemanticDiffResult 序列化） |
| diff_type | String(20) | NOT NULL, 默认 semantic | 对比方式（semantic / algorithmic） |
| created_at | DateTime | NOT NULL, 默认 UTC now | 创建时间 |

#### 关联表

| 关联表 | 连接实体 | 说明 |
|--------|----------|------|
| case_rule_node_assoc | TestCase ↔ RuleNode | 用例绑定的规则节点 (多对多) |
| case_rule_path_assoc | TestCase ↔ RulePath | 用例绑定的规则路径 (多对多) |

---

## 4. API 接口文档

后端启动后可访问 `http://localhost:8000/docs` 查看 Swagger UI 自动生成的交互式文档。

### 4.1 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 返回 `{"status": "ok"}` |

### 4.2 项目管理 (`/api/projects`)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/projects` | 创建项目 | `{name, description?}` | ProjectRead (201) |
| GET | `/api/projects` | 获取所有项目列表 (按 ID 倒序) | — | ProjectRead[] |
| GET | `/api/projects/{project_id}` | 获取单个项目详情 | — | ProjectRead |
| PUT | `/api/projects/{project_id}` | 更新项目 | `{name, description?}` | ProjectRead |
| DELETE | `/api/projects/{project_id}` | 删除项目 (级联删除关联需求/用例/分析记录) | — | 204 No Content |
| POST | `/api/projects/{project_id}/requirements` | 创建需求 | `{title, raw_text, source_type?}` | RequirementRead (201) |
| GET | `/api/projects/{project_id}/requirements` | 获取项目下需求列表 (按 ID 倒序) | — | RequirementRead[] |
| GET | `/api/projects/{project_id}/requirements/{requirement_id}` | 获取单个需求详情 | — | RequirementRead |
| PUT | `/api/projects/{project_id}/requirements/{requirement_id}` | 更新需求 | `{title, raw_text, source_type?}` | RequirementRead |
| DELETE | `/api/projects/{project_id}/requirements/{requirement_id}` | 删除需求 (级联删除关联规则节点/路径) | — | 204 No Content |

### 4.3 规则树管理 (`/api/rules`)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/rules/nodes` | 创建规则节点 | `{requirement_id, parent_id?, node_type, content, risk_level?}` | RuleNodeRead (201) |
| GET | `/api/rules/requirements/{requirement_id}/tree` | 获取完整规则树 (仅返回未软删除节点) | — | `{nodes: [], paths: []}` |
| PUT | `/api/rules/nodes/{node_id}` | 更新规则节点 (触发影响分析) | `{content?, node_type?, risk_level?, status?, parent_id?}` | `{node, impact}` |
| DELETE | `/api/rules/nodes/{node_id}` | 软删除规则节点 (触发影响分析) | — | `{ok, impact}` |
| POST | `/api/rules/impact` | 影响分析预览 | `{requirement_id, changed_node_ids}` | ImpactResult |

**关键机制：**
- 创建/更新/删除节点后，系统自动重新推导所有规则路径 (`_regenerate_paths`)
- 更新/删除节点后，系统自动执行影响分析 (`_mark_impacted_cases`)，将受影响的测试用例标记为 `needs_review`
- 创建/更新节点时会执行父链环检测，阻止 `parent_id` 形成环
- 规则树查询会过滤 `status=deleted` 节点，避免已软删除节点继续出现在前端画布

**实现位置：**
- `backend/app/api/rules.py` → `get_rule_tree` (`RuleNode.status != NodeStatus.deleted`)
- `backend/app/api/rules.py` → `_assert_parent_chain_no_cycle` (创建/更新节点的父链环检测)

### 4.4 测试用例管理 (`/api/testcases`)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/testcases` | 创建测试用例 | `{project_id, title, steps, expected_result, risk_level?, status?, bound_rule_node_ids?, bound_path_ids?}` | TestCaseRead (201) |
| GET | `/api/testcases/projects/{project_id}` | 获取项目下用例列表 (支持 `?requirement_id=N` 按需求筛选) | — | TestCaseRead[] |
| GET | `/api/testcases/{case_id}` | 获取单个用例详情 | — | TestCaseRead |
| PUT | `/api/testcases/{case_id}` | 更新测试用例 (含重绑规则节点/路径) | `{title, steps, expected_result, risk_level?, status?, bound_rule_node_ids?, bound_path_ids?}` | TestCaseRead |
| DELETE | `/api/testcases/{case_id}` | 删除测试用例 | — | 204 No Content |

**用例列表按需求筛选机制：** 当传入 `requirement_id` 参数时，通过 `outerjoin` 关联 `bound_rule_nodes` 和 `bound_paths`，筛选出绑定节点或路径属于该需求的用例。
**状态写入机制：** 创建/更新接口支持显式传入 `status`，前端新建表单和编辑弹窗都提供状态下拉供用户直接选择。
**删除行为补充：** 删除用例时会级联删除其关联的 `reco_result` 明细，避免历史推荐引用导致删除失败。

### 4.4.1 测试用例智能导入 (`/api/testcases/import`)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/testcases/import/parse` | 解析 Excel/XMind 并执行节点匹配预览 | `multipart/form-data: {file, requirement_id}` | `ImportParseResponse` |
| POST | `/api/testcases/import/confirm` | 确认批量导入测试用例并建立绑定关系 | `{project_id, requirement_id, cases[]}` | `ImportConfirmResponse` |

**`parse` 关键行为：**
- 支持 `.xlsx/.xlsm/.xmind` 文件
- Excel：自动识别表头并映射标题/步骤/预期结果字段
- XMind：按节点层级提取用例，兼容扁平与树形结构
- 匹配优先走 LLM 批量匹配，失败自动降级为关键词匹配
- 返回 `analysis_mode`（`llm` 或 `mock_fallback`）、`confidence`、`match_reason`

**`confirm` 强校验与事务规则：**
- `requirement_id` 必须归属于 `project_id`，否则 `invalid_project_requirement_relation`
- 未标记跳过的用例必须至少绑定一个规则节点，否则 `unbound_case_not_allowed`
- `bound_rule_node_ids` 必须存在且属于当前需求，否则 `invalid_bound_rule_node_ids`
- `bound_path_ids` 必须存在且属于当前需求，否则 `invalid_bound_path_ids`
- 每条绑定路径必须覆盖该条用例的全部绑定节点，否则 `path_node_mismatch`
- 批量导入使用单事务，任一条失败整批回滚

### 4.5 覆盖矩阵 (`/api/coverage`)

| 方法 | 路径 | 说明 | 响应 |
|------|------|------|------|
| GET | `/api/coverage/projects/{project_id}` | 获取项目维度覆盖矩阵 (汇总口径) | CoverageMatrix |
| GET | `/api/coverage/projects/{project_id}/requirements/{requirement_id}` | 获取需求维度覆盖矩阵 (精确口径，前端覆盖页默认使用) | CoverageMatrix |

**说明：**
- 覆盖页当前强制按“已选需求”取数，调用需求维度接口，避免误显示项目汇总节点数。
- `/api/coverage/projects/{project_id}` 仍保留用于项目级汇总统计。
- 项目维度与需求维度覆盖接口都会过滤 `status=deleted` 节点；已软删除节点不会出现在覆盖详情表，也不会计入覆盖率分母。

**实现位置：**
- `backend/app/api/coverage.py` → `_build_requirement_coverage`、`coverage_by_project` (节点查询增加 `RuleNode.status != NodeStatus.deleted`)

**CoverageMatrix 响应结构：**
```json
{
  "rows": [
    {
      "node_id": "uuid",
      "content": "节点内容",
      "risk_level": "critical",
      "covered_cases": 2,
      "uncovered_paths": 0
    }
  ],
  "summary": {
    "total_nodes": 10,
    "covered_nodes": 8,
    "coverage_rate": 0.8,
    "uncovered_critical": ["node_id_1"],
    "uncovered_paths": [["n1", "n2", "n3"]]
  }
}
```

### 4.6 AI 解析 (`/api/ai`)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/ai/parse` | 解析需求文本为规则草稿 | `{raw_text}` | `{analysis_mode, nodes: AIParseNode[]}` |

**当前实现逻辑：**
- 默认 `AI_PARSE_PROVIDER=llm`，优先使用 `LLMClient.chat_with_json` 生成草稿节点
- 若 LLM 调用失败、超时、返回空节点或结构不兼容，则自动降级为规则分句解析
- 返回 `analysis_mode` 以标识本次解析来源：
  - `llm`：LLM 解析成功
  - `mock_fallback`：先走 LLM 后降级
  - `mock`：显式关闭 LLM（如 `AI_PARSE_PROVIDER=mock`）时使用规则分句
- 兼容常见 LLM 产物形态：`nodes`、`decision_tree.nodes`、`decisionTree`，并对别名字段 (`nodeId/nodeType/parentId/text`) 做归一化

### 4.7 需求拆解 (`/api/ai/architecture`，P1+ 新增)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/ai/architecture/analyze` | 需求拆解分析 | `multipart/form-data: {project_id, requirement_id?, title?, description_text?, image?}`（`description_text` 与 `image` 至少一个） | ArchitectureAnalyzeResponse (201) |
| GET | `/api/ai/architecture/{analysis_id}` | 获取分析详情 | — | ArchitectureAnalysisRead |
| POST | `/api/ai/architecture/{analysis_id}/import` | 导入分析结果到正式库 | `{import_decision_tree?}` | ArchitectureImportResult |

**ArchitectureAnalyzeResponse 响应结构：**
```json
{
  "id": 1,
  "analysis_mode": "llm",
  "llm_provider": "openai",
  "decision_tree": {
    "nodes": [
      {"id": "dt_1", "type": "root", "content": "...", "parent_id": null, "risk_level": "medium"},
      {"id": "dt_2", "type": "condition", "content": "...", "parent_id": "dt_1", "risk_level": "high"}
    ]
  },
  "test_plan": null,
  "risk_points": [],
  "test_cases": []
}
```

**ArchitectureImportResult 响应结构：**
```json
{
  "analysis_id": 1,
  "requirement_id": 5,
  "imported_rule_nodes": 6
}
```

**关键机制：**
- 分析接口 (`/analyze`) 接受 `multipart/form-data`，支持仅流程图、仅文字、图文联合三种输入形态（但至少提供一项）
- 分析引擎通过 Provider 模式选择 (`ANALYZER_PROVIDER` 环境变量)：
  - `mock`：规则/模板分句分析
  - `llm`：两阶段 LLM 分析（阶段1 多模态理解 + 阶段2 JSON 结构化生成）
- `llm` 模式下使用 SSE（`httpx + text/event-stream`）调用多模型链路：`OpenAIClient` 优先，失败后自动回退 `ZhipuClient`；双模型都失败才回退 `MockAnalyzerProvider`
- 分析结果会返回并持久化 `analysis_mode`：
  - `llm`：本次由 LLM 成功生成
  - `mock`：本次直接使用 Mock 引擎
  - `mock_fallback`：本次先走 LLM，后因失败自动降级到 Mock
- 分析结果会返回并持久化 `llm_provider`（当启用 LLM 链路时）：
  - `openai`：本次由 OpenAI provider 实际命中
  - `zhipu`：本次由智谱 provider 实际命中（可能是 OpenAI 失败后的回退结果）
  - `null`：本次未走 LLM（如 `mock`）或 provider 不可识别
- 导入接口 (`/import`) 当前仅支持导入判断树节点（`import_decision_tree`）
- 导入时若无关联需求会自动创建新需求，并自动重算规则路径
- 上传的图片存储在 `backend/uploads/architecture/` 目录，通过 `/uploads/architecture/` 静态路径访问

### 4.8 回归推荐 (`/api/reco`，P1 新增)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/reco/regression` | 执行回归推荐并落库 | `{requirement_id, mode, k, changed_node_ids?, case_filter?, cost_mode?}` | RecoResponse |
| GET | `/api/reco/runs?requirement_id={id}` | 查询需求下推荐历史 | — | RecoRunRead[] |
| GET | `/api/reco/runs/{run_id}` | 查询单次推荐运行详情 | — | RecoRunDetailRead |

**关键机制：**
- `FULL` 模式：`universe = 当前需求全部活跃节点`
- `CHANGE` 模式：`universe = 变更影响域 (变更节点 + 祖先链 + 子树)`，并对影响域节点乘以 `change_boost=1.5`
- 风险权重由 `risk_scorer` 实时计算：`a*type_weight + b*complexity + c*change_freq + d*uncovered_bonus`
- 推荐算法由 `recommender` 执行带权集合覆盖贪心：每轮选择 `gain / cost` 最大用例
- 每次运行都会写入 `reco_run` 和 `reco_result`，并返回可解释字段：`gain_nodes`、`top_contributors`、`why_selected`

### 4.9 需求版本化 (P1+ 新增)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/projects/{project_id}/requirements/{requirement_id}/new-version` | 创建需求新版本 | — | RequirementRead (201) |
| GET | `/api/projects/{project_id}/requirements/{requirement_id}/versions` | 获取需求版本列表 | — | RequirementVersionRead[] |

**关键机制：**
- 首次创建新版本时，若 v1 的 `requirement_group_id` 为空，则将其设为 v1 的 `id`，作为版本组标识
- 新版本复制原需求的 `title`、`raw_text`、`source_type`，`version` 递增
- 版本列表按 `version desc` 排序，每个版本返回 `rule_node_count`（活跃规则节点数量）
- 规则树按版本隔离：不同版本的需求拥有独立的 `rule_nodes`，互不影响

### 4.10 规则树版本 Diff (`/api/rules/diff`，P1+ 新增)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/api/rules/diff?base_requirement_id=N&compare_requirement_id=M` | 语义级规则树版本对比（自动保存对比记录） | — | SemanticDiffResult |
| GET | `/api/rules/diff/history?project_id=N&requirement_group_id=M` | 获取对比历史列表（按时间倒序，最多 50 条） | — | DiffRecordRead[] |
| GET | `/api/rules/diff/history/{record_id}` | 获取单条对比记录详情 | — | DiffRecordRead |
| DELETE | `/api/rules/diff/history/{record_id}` | 删除对比记录 | — | `{ok: true}` |

**SemanticDiffResult 响应结构：**
```json
{
  "base_version": 1,
  "compare_version": 2,
  "summary": "总体变更摘要",
  "key_changes": [
    "核心变化要点 1",
    "核心变化要点 2"
  ],
  "flow_changes": [
    {
      "change_type": "added|removed|modified",
      "title": "变更标题",
      "before": "旧版本的具体业务行为",
      "after": "新版本的具体业务行为",
      "description": "变更说明",
      "detail": "可选，进一步解释",
      "impact": "low|medium|high",
      "test_suggestion": "可选，建议如何验证"
    }
  ],
  "risk_notes": "可选，兼容旧记录的文本风险提示",
  "risks": [
    {
      "risk": "具体风险点",
      "suggestion": "建议的验证方式"
    }
  ]
}
```

**DiffRecordRead 响应结构：**
```json
{
  "id": 1,
  "base_requirement_id": 1,
  "compare_requirement_id": 2,
  "base_version": 1,
  "compare_version": 2,
  "diff_type": "semantic",
  "created_at": "2026-03-06T12:00:00",
  "result": { "...SemanticDiffResult..." }
}
```

**关键机制：**
- 优先使用 LLM 进行语义级 Diff，生成面向业务读者的 `summary`、`key_changes`、`flow_changes` 和 `risks`
- LLM Diff 失败时自动回退到算法 Diff（基于节点内容模糊匹配 + SequenceMatcher）
- `FlowChange` 支持 `title / before / after / detail / test_suggestion`，用于前端展示旧/新行为对照和测试建议
- 后端会清洗 `change_type`、`impact`、`key_changes`、`risks` 等字段，并按影响等级 `high -> medium -> low` 排序
- `risk_notes` 仍保留为兼容字段；前端优先展示结构化 `risks`，缺失时再回退为纯文本风险提示
- 序列化使用缩进文本格式传递给 LLM，提高语义理解准确度
- 每次执行 Diff 后自动将结果保存为 `DiffRecord`，保存失败不影响 Diff 结果返回
- 历史记录列表支持按 `project_id` 过滤，可选按 `requirement_group_id` 进一步缩小范围

### 4.11 规则树会话式 AI 生成 (`/api/rules/sessions`，P1+ 新增)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/rules/sessions` | 创建会话 | `{requirement_id, title?}` | RuleTreeSessionRead (201) |
| GET | `/api/rules/sessions?requirement_id=N` | 获取会话列表 | — | RuleTreeSessionRead[] |
| GET | `/api/rules/sessions/{session_id}` | 获取会话详情（含消息历史） | — | RuleTreeSessionDetailRead |
| POST | `/api/rules/sessions/{session_id}/generate` | 生成规则树 | `{user_input?}` | RuleTreeGenerateResponse |
| POST | `/api/rules/sessions/{session_id}/update` | 增量更新规则树 | `{user_input}` | RuleTreeUpdateResponse |
| POST | `/api/rules/sessions/{session_id}/confirm` | 确认并导入规则树 | `{tree_data}` | RuleTreeConfirmResponse |

**关键机制：**
- 生成流程：用户输入 → LLM 生成规则树 → LLM 自动审查 → 返回结果 + 审查意见
- 增量更新：基于已有规则树和用户反馈/新需求，LLM 生成更新后的规则树
- 确认导入：将最终规则树写入正式 `rule_nodes` 表，清理旧节点后插入新节点并重算路径
- 消息持久化：每轮交互都会记录 `user_input`、`generation`、`review`、`update` 等消息到 `rule_tree_messages`
- 支持需求文本快照：创建会话时保存需求原文，确保后续交互基于创建时的需求版本

### 4.12 风险识别分析 (`/api/risks`，P1+ 新增)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/ai/risks/analyze` | AI 风险识别分析 | `{requirement_id}` | RiskAnalyzeResponse (201) |
| GET | `/api/rules/requirements/{requirement_id}/risks` | 获取需求下风险列表 | — | RiskListResponse |
| PUT | `/api/rules/risks/{risk_id}/decision` | 风险决策（接受/忽略） | `{decision, reason, auto_create_node?}` | RiskItemRead |
| DELETE | `/api/rules/risks/{risk_id}` | 删除风险项 | — | 204 No Content |
| POST | `/api/rules/risks/{risk_id}/to-node` | 风险转为规则节点 | — | RuleNodeRead (201) |

**关键机制：**
- 基于需求文本和规则树结构，通过 LLM 识别潜在风险点
- 风险分析属于长耗时 LLM 接口，前端对 `/api/ai/risks/analyze` 单独使用长超时配置，避免沿用全局短超时后出现"前端先报失败、后端仍在继续执行"的假失败体验
- 同一 `requirement_id` 的并发风险分析请求会在服务层合并：首个请求执行真实分析，后续重复请求等待首轮完成后直接返回最新结果，避免短时间内多次触发 LLM
- 每次重新分析都会先清空该需求下旧的 `risk_items` 再写入新结果，确保风险列表是"本轮分析快照"，避免重复记录累积
- 用户可对每条风险项进行决策（接受/忽略/转节点/删除）
- "转节点"将风险项直接转化为规则树节点，增强规则覆盖范围
- 删除操作通过前端 Popconfirm 二次确认后执行，物理删除风险记录

### 4.13 测试方案与用例生成 (`/api/test-plan`，P1+ 新增)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/api/test-plan/sessions?requirement_id=N` | 获取需求下测试方案会话列表 | — | TestPlanSessionListResponse |
| GET | `/api/test-plan/sessions/{session_id}` | 获取会话详情 | — | TestPlanSessionResponse |
| POST | `/api/test-plan/sessions` | 创建会话（自动归档同需求下已有活跃会话） | `{requirement_id}` | TestPlanSessionResponse |
| PUT | `/api/test-plan/sessions/{session_id}/archive` | 归档会话 | — | TestPlanSessionResponse |
| PUT | `/api/test-plan/sessions/{session_id}/plan` | 更新测试方案（用户编辑后保存） | `{plan_markdown, test_points}` | TestPlanSessionResponse |
| PUT | `/api/test-plan/sessions/{session_id}/cases` | 更新会话中的用例列表（删除用例时同步） | `GeneratedTestCase[]` | TestPlanSessionResponse |
| POST | `/api/test-plan/generate` | AI 生成测试方案 | `{requirement_id, session_id?}` | TestPlanResponse |
| POST | `/api/test-plan/generate-cases` | AI 基于测试方案生成测试用例 | `{requirement_id, test_plan_markdown, test_points, session_id?}` | TestCaseGenResponse |
| POST | `/api/test-plan/confirm-cases` | 确认导入测试用例到用例库 | `{requirement_id, test_cases, session_id?}` | TestCaseConfirmResponse |

**关键机制：**
- **两阶段生成**：先生成测试方案（Markdown + 测试点列表），再基于方案生成具体测试用例
- **会话管理**：每次生成操作关联到 `TestPlanSession`，支持状态追踪和历史回溯
- **手工导入入口**：前端支持导入本地 Markdown 方案并写入 `TestPlanSession.plan_markdown`，可跳过 AI 方案生成阶段，从人工编写方案直接进入审核/生成用例流程
- **覆盖保障**：生成后自动检查所有可测试节点（action/branch/exception）是否被覆盖，未覆盖的自动补充兜底测试点/用例
- **节点 ID 校验**：生成的 `related_node_ids` 会过滤无效 ID，确保只引用规则树中存在的节点
- **空测试点容错**：即使当前会话没有结构化 `test_points`，仍可基于 `plan_markdown` 继续生成测试用例，由 AI 在阶段2自动抽取测试点语义
- **确认导入**：确认时将生成的用例写入 `test_cases` 表，自动绑定关联规则节点
- **会话自动归档**：创建新会话时自动归档同需求下的活跃会话，确保同一需求只有一个活跃会话

---

## 5. 核心业务逻辑

### 5.1 规则路径推导 (`rule_engine.py`)

**算法:** DFS (深度优先搜索) 从根节点到叶子节点遍历所有路径。

**输入:** 节点列表 `[{id, parent_id}]`

**输出:** 所有根到叶的路径 `[[node_id, ...], ...]`

**流程：**
1. 按 `parent_id` 构建父子映射
2. 找到所有根节点 (`parent_id == None`)
3. 从每个根节点 DFS 递归，使用 `visited` 集合跳过已访问节点，避免环导致递归溢出
4. 返回所有路径

**触发时机：** 每次规则节点创建/更新/删除后自动调用

**环保护机制：**
- 路径推导时：`derive_rule_paths` 中 DFS 引入 `visited` 集合
- 节点写入时：`rules.py` 在 create/update 场景校验父链，若检测到回指自身或闭环则返回 400

### 5.2 覆盖率矩阵计算 (`coverage.py`)

**输入：**
- 规则节点列表 (含 risk_level)
- 测试用例列表 (含绑定的节点 ID)
- 规则路径列表

**计算逻辑：**
1. 统计每个节点被多少测试用例覆盖
2. 检查每条路径是否至少有一个节点被覆盖，未覆盖则标记
3. 计算覆盖率 = `covered_nodes / total_nodes`
4. 标记未覆盖的 critical 节点（高风险告警）

### 5.3 变更影响分析 (`impact.py`)

**输入：**
- 变更的节点 ID 列表
- 所有测试用例 (含绑定关系)
- 规则路径列表

**逻辑：**
1. 遍历所有测试用例
2. 如果用例绑定的规则节点与变更节点有交集，则标记该用例
3. 将受影响的用例状态更新为 `needs_review`
4. 返回受影响的用例 ID 列表

### 5.4 AI 需求解析 (`ai_parser.py`)

**当前版本为 LLM 优先 + 规则分句兜底：**
1. 若 `AI_PARSE_PROVIDER` 允许 LLM（`llm/auto`），先调用 `LLMClient.chat_with_json`
2. 对返回结构执行归一化（支持 `nodes`、`decision_tree.nodes`、`decisionTree` 与字段别名）
3. 修复树结构（确保单 root、非法 parent 自动挂回 root）
4. 若 LLM 失败或产物不可用，回退到规则分句解析（按逗号切分、线性父子链）
5. 返回 `{analysis_mode, nodes}`，前端弹窗据此展示“解析引擎”标签（LLM / Mock（LLM降级）/ Mock）

### 5.5 需求拆解 (`architecture_analyzer.py`，P1+ 新增)

**架构模式：** Provider 模式，通过 `ANALYZER_PROVIDER` 环境变量选择分析引擎。

**Provider 层级：**
- `ArchitectureAnalyzerProvider` — 抽象基类
- `MockAnalyzerProvider` — 规则/模板分析引擎 (当前默认)
- `LLMAnalyzerProvider` — 两阶段 LLM 分析引擎（SSE 通道）
- `LLMClient`（服务层）内部使用 `FallbackLLMClient` 串联 `OpenAIClient -> ZhipuClient`
- Provider 暴露 `get_analysis_mode()`，API 层在 `/api/ai/architecture/analyze` 返回并落库该字段，供前端展示本次引擎来源

**LLMAnalyzerProvider 分析流程（两阶段）：**
1. **阶段1（可选）多模态理解**：若存在流程图，调用 `LLMClient.chat_with_vision`（图 + 文）生成架构理解文本；纯文本场景会跳过此阶段。阶段1结果会做长度保护（当前上限 4000 字符），避免超长输入影响阶段2稳定性
2. **阶段2 结构化生成**：调用 `LLMClient.chat_with_json`，强制 JSON Mode 输出 `decision_tree`
3. **结果校验与兜底**：
   - 先按 `ArchitectureAnalysisResult` Pydantic Schema 校验结构
   - 若校验失败，先尝试“结构归一化”修正常见漂移
   - 归一化支持包裹层与别名字段：如 `data/result/output` 包裹、`decisionTree`、`nodeId/nodeType/risk/level` 等
   - 归一化后再次执行 Schema 校验与 `related_node_ids` 引用校验
   - 仅当原始校验与归一化校验都失败时，才回退 `MockAnalyzerProvider`
4. **后处理增强（校验成功后执行）**：
   - 同级节点去重：按 `parent_id + type + 归一化 content` 做精确去重，避免明显重复节点
   - 子节点重挂载：被去重节点的子节点会重挂到保留节点，保持树连通性
   - 节点数量观测：`<15` 或 `>40` 记录 warning 日志，仅告警不拦截流程

**LLMClient（`llm_client.py`）能力：**
- 基于多 provider 调用：OpenAI 侧使用 `openai` SDK（支持 `base_url` 网关），智谱侧使用 SSE（`httpx + text/event-stream`）
- 默认回退顺序：OpenAI 优先，智谱兜底（上层仍保持 `LLMClient()` 零侵入调用）
- 支持多模态调用与 JSON 结构化调用（`response_format=json_object`）
- 支持通用消息列表调用 `chat_with_messages(messages, response_format?)`，用于会话式 AI 交互（P1+ 新增）
- 支持重试与超时控制（`LLM_MAX_RETRIES` / `LLM_CONNECT_TIMEOUT` / `LLM_REQUEST_TIMEOUT`）
- 支持 `max_tokens/temperature/seed` 参数透传；`thinking` 仅对智谱 provider 生效
- 支持流式响应增量拼接与稳健 JSON 提取（可从包裹文本中抽取对象，支持双重 JSON 编码解码）
- SSE 事件解析兼容 `httpx==0.24.1`（`iter_lines()` 不带 `decode_unicode` 参数，统一兼容 `bytes/str`）
- 增加调用链日志：请求起始、重试、HTTP 非 200 响应摘要、SSE 空内容告警、JSON 恢复解析日志
- 支持本地图片转 `data:` URL（base64）并做图片大小上限保护

**Prompt 管理：**
- `backend/app/services/prompts/architecture.py` 统一维护需求拆解阶段1/阶段2 Prompt 模板
- `backend/app/services/prompts/rule_tree_session.py` 维护规则树会话式 AI 生成相关 Prompt（生成模板 / 审查提示 / 增量更新模板）（P1+ 新增）
- `backend/app/services/prompts/risk_analysis.py` 维护风险识别分析 Prompt（P1+ 新增）
- `backend/app/services/prompts/test_plan.py` 维护测试方案与用例生成 Prompt（方案生成模板 / 用例生成模板）（P1+ 新增）

**MockAnalyzerProvider 分析流程（兜底引擎）：**

1. **组装分析输入** (`_compose_analysis_description`) — 统一组合文本与流程图提示信息
   - 仅文字：直接使用文字描述
   - 仅流程图：生成「流程图参考信息：{文件名提示}」作为分析文本
   - 图文联合：将文字描述与流程图提示拼接后再进入后续流程
2. **文本分句** (`_split_sentences`) — 按句号/叹号/问号/分号/换行拆分
3. **构建判断树** (`_build_decision_tree`)
   - 第一句作为 root 节点
   - 后续每句尝试拆分「条件-动作」对 (按「则」「那么」「->」「，」分割)
   - 条件部分判断是否含 condition 关键词 (如果/当/若/是否/检查/校验)
   - 动作部分判断是否为异常文本 (异常/失败/超时/错误/拒绝)
   - 所有条件/分支节点直接挂在 root 下，动作节点挂在对应条件下
4. **统一返回结构** (`_decision_tree_only_result`)
   - 当前仅返回 `decision_tree`
   - `test_plan` 固定为 `null`，`risk_points/test_cases` 固定为空数组

**风险等级自动推断 (`_content_to_risk`)：**
- critical: 包含「资金/转账/并发/安全/权限/超时」
- high: 包含「失败/异常/错误/拒绝/重试」
- medium: 包含「检查/校验/不足」
- low: 其他

**导入流程 (`architecture.py` API 层)：**
1. 判断树导入 — 按拓扑顺序 (父先子后) 将节点写入 RuleNode 表，维护 ID 映射
2. 导入完成后自动重算规则路径 (`_regenerate_paths`)
3. 若无关联需求，自动创建新 Requirement (source_type=flowchart)

### 5.6 风险权重计算 (`risk_scorer.py`，P1 新增)

**目标：** 为推荐算法提供节点风险分数 `risk_score`。

**公式：**
`risk_score = a*type_weight + b*complexity + c*change_freq + d*uncovered_bonus`

- `type_weight`: `critical=4, high=3, medium=2, low=1`
- `complexity`: `children_count / max_children`
- `change_freq`: `version / max_version`
- `uncovered_bonus`: 节点未被任何候选用例覆盖时为 `1`，否则为 `0`
- 默认系数：`a=3.0, b=1.0, c=1.5, d=2.0`

### 5.7 覆盖集合计算 (`cover_set.py`，P1 新增)

**目标：** 计算每个用例对规则节点的覆盖集合 `Cover(c)`。

**定义：**
`Cover(c) = 绑定节点 ∪ 绑定路径上的所有节点`

**实现要点：**
- 直接读取 `TestCase.bound_rule_nodes` 与 `TestCase.bound_paths`
- 通过 `RulePath.node_sequence` 解析路径节点序列
- 产出 `cover_sets: Dict[case_id, Set[node_id]]`

### 5.8 贪心推荐算法 (`recommender.py`，P1 新增)

**目标：** 在回归`K`内选择风险收益最大的最小回归用例集。

**流程：**
1. 初始化 `covered = ∅`
2. 每轮遍历候选用例，计算 `new_cover = Cover(c) ∩ universe - covered`
3. 计算 `gain = Σ risk_weights[n] (n ∈ new_cover)`
4. 按 `gain/cost` 选最大（当前 `cost_mode=UNIT`，每条用例成本为 1）
5. 更新 `covered` 并记录解释信息（`gain_node_ids`、`top_contributors`、`why_selected`）
6. 停止条件：达到 `K` 或无正收益

### 5.9 变更影响域 (`impact_domain.py`，P1 新增)

**目标：** 为 CHANGE 模式计算推荐目标域。

**影响域定义：**
- 变更节点本身
- 变更节点的祖先链 (沿 `parent_id` 向上)
- 变更节点的子树 (沿 children 向下 DFS)

**在推荐中的使用：**
- CHANGE 模式下 `universe = impact_domain`
- 影响域节点风险值额外乘以 `change_boost` (默认 1.5)

### 5.10 规则树版本 Diff (`tree_diff.py`，P1+ 新增)

**目标：** 语义级对比两个版本的规则树差异，输出可读的变更报告。

**双模式策略：**
1. **LLM 语义 Diff（优先）**：将两棵规则树序列化为缩进文本 → 交给 LLM 进行语义级对比 → 返回 `summary`（变更摘要）、`key_changes`（关键变化要点）、`flow_changes`（流程级变更列表）和 `risks`（结构化风险提示）
2. **算法 Diff（兜底）**：当 LLM 调用失败时，使用基于 `SequenceMatcher` 的模糊匹配算法，按内容相似度对比节点，输出 `added`、`removed`、`modified`、`unchanged` 四类节点列表

**树序列化方式：**
- 递归遍历规则树，按缩进层级生成可读文本
- 格式：`[类型] 内容 (风险等级: xxx)`，子节点缩进两个空格

**LLM 输出约束与清洗：**
- Prompt 明确要求使用 PM / QA / 开发都能直接读懂的业务语言，禁止输出节点 ID、UUID 或抽象术语堆砌
- `flow_changes` 中每条记录要求补齐 `title`、`before`、`after`、`description`、`impact`，并可选给出 `detail` 与 `test_suggestion`
- `key_changes` 控制为 2~5 条短句，适合在前端摘要区快速浏览
- `risks` 采用 `{risk, suggestion}` 结构，便于前端拆分展示“风险点”和“验证建议”
- 服务端会过滤非法 `change_type` / `impact` 值、去除空字符串，并将流程变更按 `high -> medium -> low` 排序

**前端消费约定：**
- 摘要区优先显示 `summary + key_changes`
- 风险区优先显示结构化 `risks`，历史旧记录若仅有 `risk_notes` 仍可回显
- 流程级变更优先展示 `before/after` 对照；若缺失则回退展示 `description`

### 5.11 规则树会话式 AI 生成 (`rule_tree_session.py`，P1+ 新增)

**目标：** 通过多轮对话式交互，由 AI 生成、审查和迭代优化规则树，最终确认导入正式库。

**核心流程：**
1. **创建会话** — 关联需求、保存需求文本快照、初始化消息历史
2. **生成规则树** — 用户提供需求描述 → LLM 生成规则树（JSON 格式） → LLM 自动审查质量 → 返回生成结果和审查意见
3. **增量更新** — 用户提供修改意见 → LLM 基于已有树和反馈生成更新后的规则树 → 计算新旧树 diff
4. **确认导入** — 将最终树写入正式 `rule_nodes` 表，删除旧节点 → 插入新节点 → 重算规则路径

**消息持久化机制：**
- 每轮交互产生的输入、生成结果、审查意见、更新请求均记录为 `RuleTreeMessage`
- `message_type` 区分消息类型：`user_input`、`generation`、`review`、`update`、`confirm`
- `tree_snapshot` 存储每步的规则树 JSON 快照，支持回溯查看历史状态

**树规范化：**
- 确保每棵生成的树有唯一 root 节点
- 所有节点 ID 使用 `dt_` 前缀统一规范
- 校验 `parent_id` 引用完整性

### 5.12 风险识别分析 (`risk_service.py`，P1+ 新增)

**目标：** 基于需求文本和规则树结构，利用 AI 自动识别潜在风险点。

**核心流程：**
1. 收集需求文本和规则树全量节点信息
2. 通过 LLM 分析输出风险项列表（含风险描述、严重程度、建议处理方式）
3. 服务层按 `requirement_id` 做并发合并：同一需求已有分析进行中时，后续重复请求阻塞等待，不再重复触发第二次 LLM 调用
4. 每轮分析落库前先删除该需求已有 `RiskItem`，再批量写入新风险项，保证风险列表只保留最新一轮结果
5. 用户逐条决策：接受（标注为已识别风险）、忽略（跳过该风险）、转节点（将风险转化为新的规则节点加入树中）、删除（物理删除该风险项）
6. "转节点"操作会创建新的 `RuleNode` 并自动重算路径
7. "删除"操作通过前端 Popconfirm 二次确认后执行，物理删除风险记录

**稳定性约束：**
- `frontend/src/api/risks.ts` 对风险分析接口使用 `180000ms` 超时，和规则树会话、测试方案等长耗时 LLM 接口保持一致
- `backend/app/services/risk_service.py` 使用进程内条件变量跟踪分析中状态，确保单进程部署下同一需求不会并发跑多轮风险分析
- `backend/tests/test_risk_service.py` 覆盖"两个并发请求只触发一次 LLM，最终仅保留一份风险结果"回归场景

### 5.13 测试方案与用例生成 (`test_plan_generator.py`，P1+ 新增)

**目标：** 基于规则树结构，通过 AI 两阶段生成测试方案和测试用例，最终确认导入用例库。

**两阶段流程：**

1. **阶段1 — 生成测试方案** (`generate_test_plan`)：
   - 将规则树节点和路径序列化为 JSON 传给 LLM
   - LLM 输出 Markdown 格式的测试方案 + 结构化测试点列表（`test_points`）
   - 后处理：校验 `related_node_ids` 引用有效性，自动补充未覆盖的可测试节点（action/branch/exception）

2. **阶段2 — 生成测试用例** (`generate_test_cases`)：
   - 将测试方案 Markdown、测试点列表、规则树节点和路径传给 LLM
   - LLM 输出结构化测试用例列表（含标题、前置条件、步骤、预期结果、风险等级、关联节点）
   - 后处理：校验节点引用，自动补充未覆盖节点的兜底用例

**覆盖保障机制：**
- 可测试节点定义：`node_type ∈ {action, branch, exception}`
- 阶段1/阶段2均会检查覆盖率，未被任何测试点/用例关联的可测试节点会自动补充兜底项

**会话管理：**
- 每次生成操作可关联到 `TestPlanSession`，状态随流程推进自动流转
- 创建新会话时自动归档同需求下的活跃会话
- 前端支持从本地 `.md` 文件导入测试方案，导入后先以空 `test_points` 初始化会话，再由用户补充或在生成用例阶段自动抽取
- 用户可在方案生成后编辑保存（`update_session_plan`），也可在用例列表中移除用例（`update_session_cases`）

**确认导入：**
- 确认时将用例写入 `test_cases` 表，自动绑定 `related_node_ids` 到 `bound_rule_nodes`
- 前置条件（`preconditions`）、步骤（`steps`）、预期结果（`expected_result`）从数组序列化为可读文本存储

---

## 6. 前端页面说明

### 6.1 应用布局

```
┌─────────────────────────────────────────────────────┐
│ 侧边栏 (Sider)          │ 顶栏 (Header)              │
│                          │ [项目选择器] [需求选择器]      │
│ ○ 项目与需求             ├───────────────────────────────┤
│ ○ 规则树                 │                               │
│ ○ 用例管理               │        内容区域 (Content)      │
│ ○ 覆盖矩阵               │                               │
│ ○ 回归推荐               │                               │
│ ○ 需求拆解               │                               │
└──────────────────────────┴───────────────────────────────┘
```

**全局状态 (Zustand Store):**
- `selectedProjectId` — 当前选中的项目 (切换时自动清空 `selectedRequirementId`)
- `selectedRequirementId` — 当前选中的需求
- `projects` / `requirements` — 缓存的列表数据

**顶部筛选器显示规则：**
- 需求下拉框展示为 `需求标题 (#ID)`，用于区分同名需求，避免误选导致统计口径混淆。

**枚举标签工具 (`utils/enumLabels.ts`):**
- `riskLevelLabels` / `nodeTypeLabels` / `testCaseStatusLabels` / `sourceTypeLabels` — 枚举值到中文标签的映射 Record
- `getRiskLevelLabel()` / `getNodeTypeLabel()` / `getTestCaseStatusLabel()` / `getSourceTypeLabel()` — 安全获取中文标签的辅助函数，入参为空时返回 `"-"`

### 6.2 页面功能矩阵

| 页面 | 路由 | 核心功能 |
|------|------|----------|
| **项目与需求** | `/` | 项目 CRUD (列表/新建/查看/编辑/删除)、需求 CRUD (列表/新建/查看/编辑/删除) |
| **规则树** | `/rule-tree` | simple-mind-map 思维导图规则树、节点 CRUD、画布改动自动同步、AI 解析导入、变更影响提示、版本管理与对比、会话式 AI 生成、测试方案生成/导入、风险识别面板 |
| **用例管理** | `/test-cases` | 用例 CRUD (新建/查看/编辑/删除)、绑定规则节点/路径、按需求筛选、路径校验、状态标签 |
| **覆盖矩阵** | `/coverage` | 按当前选中需求展示覆盖率仪表盘、高风险告警、节点覆盖详情表 |
| **回归推荐** | `/recommendation` | 执行 FULL/CHANGE 推荐、查看推荐解释、查看历史 run、跳转用例并高亮 |
| **需求拆解** | `/architecture` | 上传流程图和/或填写描述进行 AI 分析，展示判断树并支持导入到规则树 |

### 6.3 项目与需求页面交互流程

**布局：** 左右两栏 (9:15 比例)，左栏项目列表 (List)，右栏需求表格 (Table)

**项目操作：**
1. 点击「新建项目」→ Modal 表单 (名称 + 描述)
2. 项目列表每行含「查看」「修改」「删除」操作按钮
3. 「查看」→ Descriptions 详情弹窗 (只读)
4. 「修改」→ Modal 表单 (预填当前值)
5. 「删除」→ Popconfirm 确认后调 DELETE API (级联删除)
6. 点击项目行 → 设为当前选中项目，右栏自动加载该项目需求

**需求操作：**
1. 点击「新建需求」→ Modal 表单 (标题 + 原文)
2. 需求表格展示 ID / 标题 / 版本 (Tag `vN`) / 来源类型 (中文标签)，每行含「查看」「修改」「删除」
3. 「修改」→ Modal 表单含来源类型 Select (需求文档/流程图/接口文档)
4. 点击需求行 → 设为当前选中需求

### 6.4 规则树页面交互流程

1. 选择需求 → 加载规则树，前端将 `RuleNode[]` 通过 `dataAdapter` 转为 `MindMapTreeNode`，由 simple-mind-map 渲染
2. 页面采用「左侧规则目录 + 右侧思维导图」双栏；目录支持关键字过滤、展开全部、仅根节点
3. 点击左侧目录节点 → 画布执行聚焦与高亮；左键点击画布节点 → 选中并聚焦；右键点击画布节点 → 弹出上下文菜单（编辑 / 新增子节点 / 删除）
4. 画布编辑（拖拽改父子关系、文本调整等）触发 `data_change`，前端基于新旧树 diff 并节流 420ms 同步后端 CRUD
5. 同步顺序为「先建新增节点 → 再更新已有节点 → 最后删除缺失节点」，并处理临时 ID 到真实 ID 的映射
6. 同步成功后提示新增/更新/删除计数，并展示影响分析 Alert（受影响用例标记为 `needs_review`）
7. 工具栏支持：新增节点、AI 半自动解析、AI 生成测试方案、文本宽度调节、适应画布、导出 PNG/SVG/XMind/Markdown
8. 点击「AI 半自动解析」→ 输入需求文本 → 生成草稿表格预览 → 确认导入
   - 草稿区会显示“解析引擎”提示（`LLM` / `Mock（LLM降级）` / `Mock`），用于现场判断质量来源
9. 新增节点 → Modal 表单，可选择父节点

**版本管理 (P1+ 新增)：**
10. 工具栏新增版本选择器下拉框，展示当前需求所有版本 (`v1`, `v2`, ...)
11. 点击「创建新版本」→ 基于当前版本创建新版本，自动跳转到新版本
12. 选择旧版本 → 页面进入只读模式，禁用编辑/新增/删除/AI解析等操作
13. 点击「版本对比」→ 弹窗展示两个版本的语义 Diff，弹窗包含两个 Tab：
    - 「新对比」Tab：选择基准/对比版本并执行 Diff，顶部 `Alert` 展示摘要；若存在 `key_changes`，以要点列表补充“这次具体改了什么”
    - 风险区优先展示结构化 `risks`（风险点 + 验证建议），兼容旧记录中的 `risk_notes` 文本提示
    - 流程级变更表展示「变更类型 / 变更内容 / 影响」三列；`变更内容` 支持 `title + before/after` 直观对照，展开行展示 `detail` 与 `test_suggestion`
    - 「历史记录」Tab：展示已保存的对比记录列表，支持查看详情和删除

**会话式 AI 生成 (P1+ 新增)：**
14. 点击「AI 生成规则树」→ 打开右侧抽屉 (Drawer)，可创建新会话或选择历史会话
15. 输入需求描述 → AI 生成规则树 + 自动审查 → 展示生成结果和审查意见
16. 对生成结果可进行增量更新：输入修改意见 → AI 基于原树和反馈重新生成
17. 确认满意后点击「确认导入」→ 规则树写入正式库，清理旧节点并重算路径
18. 会话消息历史中，AI 生成的消息（含 `tree_snapshot`）支持「应用此版本到规则树」操作，可从历史消息恢复特定版本的规则树

**风险识别面板 (P1+ 新增)：**
19. 工具栏新增「风险识别」按钮，点击后底部展开 RiskPanel
20. AI 分析当前规则树识别潜在风险点，每条风险可操作：接受 / 忽略 / 转为规则节点 / 删除
21. 删除操作通过 Popconfirm 二次确认后执行，物理删除该风险记录
22. 风险高亮：存在风险的节点在思维导图中以特殊标记显示（通过 `dataAdapter` 中的 `nodeRiskMap` 实现）
23. 存在待处理（pending）风险项时，「分析」按钮禁用并提示"请先处理所有待处理风险项"
24. 风险分析完成或决策处理后，通过 `onRisksChange` 回调同步更新父组件的风险状态

**测试方案抽屉 (P1+ 新增)：**
25. 点击「AI 生成测试方案」→ 打开右侧抽屉，展示三步流程：生成测试方案 → 审核测试方案 → 生成并导入用例
26. 第一步支持两种入口：直接调用 AI 生成测试方案，或导入本地 `.md` 文件作为测试方案初稿；导入后会自动创建新会话并进入编辑态
27. 规则树工具栏支持导出 Markdown，可将当前规则树导出为 Markdown 文本，作为手工编写测试方案的骨架
28. 审核阶段支持直接编辑 Markdown 和测试点列表；当当前没有测试点时，页面展示信息提示，允许用户手动补充测试点，或直接继续生成用例
29. 直接生成用例时，AI 会根据测试方案 Markdown 自动提取测试点，不强依赖前一步已存在结构化测试点
30. 抽屉保留历史会话列表，支持查看历史方案、恢复已生成用例并重新导入

### 6.5 用例管理页面交互流程

**布局：**
1. 默认进入页面时，新建用例表单为折叠状态，仅展示用例列表（全宽）
2. 用例列表卡片右上角提供「展开新建用例 / 收起新建用例」切换按钮
3. 展开后为左右两栏 (10:14 比例)：左栏新建用例表单，右栏用例列表

**创建用例：**
1. 填写标题/步骤/预期结果/风险等级/状态
2. 选择绑定规则节点 (多选，必填至少一个)
3. 选择绑定规则路径 (多选，可选；路径下拉框自动过滤：仅展示包含已选全部节点的路径)
4. 切换已选节点后，不匹配的路径自动被移除并提示

**用例列表：**
1. 表格展示 ID / 标题 / 执行步骤 / 预期结果 / 绑定节点 / 风险 (Tag) / 状态 (Tag) / 节点数
2. 风险 Tag 颜色按等级区分：`critical=red`、`high=volcano`、`medium=gold`、`low=green`
3. 状态 Tag 颜色按状态区分：`active=green`、`needs_review=orange`、`invalidated=red`
4. 标题、执行步骤、预期结果、绑定节点内容采用单行省略展示，鼠标悬浮 Tooltip 查看完整内容
5. 表格开启横向滚动；折叠新建区时滚动宽度更小，展开新建区时滚动宽度更大
6. 每行含「修改」「查看」「删除」操作
7. 「查看」→ 调用 `GET /api/testcases/{case_id}` → Descriptions 弹窗展示详情，绑定节点/路径以内容名称显示
   - 详情弹窗对长文本启用自动换行，内容区支持纵向滚动，避免长标题/长路径撑出弹窗
8. 「修改」→ Modal 表单预填当前值，支持修改绑定关系与状态
9. 「删除」→ Popconfirm 确认后调 DELETE API
10. 页面底部有「变更影响分析提示」Alert，说明规则更新后用例会自动标记
11. 支持通过 URL 参数 `focusCaseId` 定位高亮用例行（来自回归推荐页“查看用例”一键跳转）
12. 高亮行会自动滚动到可视区域中部，8 秒后自动取消高亮

**需求筛选：** 页面加载时传入当前选中的 `selectedRequirementId`，通过 `?requirement_id=N` 参数筛选用例

### 6.6 需求拆解页面交互流程 (P1+ 新增)

**页面布局：**
- 上半部分：左侧为流程图拖拽上传区 (Upload.Dragger)，右侧为表单 (标题 + 文字描述 textarea)
- 下半部分：分析完成后显示判断树结果面板（复用 `MindMapWrapper` 只读渲染）

**操作流程：**
1. 选择项目 → 填写需求标题 → 上传流程图和/或填写需求文字描述（至少一个）
2. 点击「开始分析」→ 调用 `/api/ai/architecture/analyze`（若图文同时提供则联合分析）→ 返回判断树结果
3. 「判断树」→ `DecisionTreeNode[]` 转换为思维导图数据并渲染；结果加载后自动执行 `fitView`
4. 底部仅保留「导入判断树」选项 → 点击「导入到正式库」→ 写入规则树
5. 上传控件文件读取兼容 `UploadFile.originFileObj` 与原始 `File`，避免“列表已显示文件但校验仍提示未上传”的误判
6. 分析结果区会展示“分析引擎”标签：`LLM/Mock/Mock（LLM降级）`，并在 LLM 链路场景额外展示 `LLM: OpenAI` 或 `LLM: Zhipu`

### 6.7 覆盖矩阵页面展示

- **前置条件** — 必须已选中项目和需求；未选需求时页面提示「请先选择需求，再查看该需求的节点覆盖率」
- **取数口径** — 覆盖页调用 `/api/coverage/projects/{project_id}/requirements/{requirement_id}`，只统计当前需求的规则节点
- **软删除过滤** — 已软删除节点不会出现在覆盖矩阵列表，也不会计入“总节点数”
- **覆盖率圆环图** — 以百分比展示当前需求节点覆盖率（例如需求 A 有 14 个节点则显示 `x/14`，需求 B 有 1 个节点则显示 `x/1`）
- **高风险告警卡片** — 列出当前需求中所有 critical 且未覆盖的节点
- **覆盖详情表** — 每行一个当前需求规则节点，展示风险等级、覆盖用例数、未覆盖路径数，支持按风险权重排序

### 6.8 回归推荐页面交互流程 (P1 新增)

1. 选择项目 + 需求后进入回归推荐页，页面自动加载规则节点与当前需求用例标题映射
2. 配置推荐参数：
   - 模式：`FULL` / `CHANGE`
   - 回归K：`K`
   - 用例状态过滤：`active / needs_review / invalidated`
   - CHANGE 模式需选择变更节点
3. 点击「开始推荐」→ 调用 `POST /api/reco/regression`
4. 页面展示本次结果：
   - 摘要：选中用例数、覆盖风险值、目标风险值、风险覆盖率
   - 推荐明细：顺位、收益风险值、新增覆盖节点、推荐原因
   - 剩余高风险缺口节点
5. 页面展示历史运行列表（`GET /api/reco/runs`）和详情（`GET /api/reco/runs/{id}`）
6. 在“本次结果”与“历史详情”中点击「查看用例」，会跳转到 `/test-cases?focusCaseId={case_id}` 并触发目标用例高亮
7. 切换需求后会清空上一个需求的“本次推荐结果/运行详情”；仅当当前需求存在对应 run 时才显示详情区块
8. 若当前需求暂无测试用例，点击「开始推荐」会提示“请先创建用例后再执行推荐”，并阻止请求发送

---

## 7. 数据库配置

### 7.1 连接配置

通过环境变量 `DATABASE_URL` 控制，默认值为 SQLite：

```
sqlite:///./test_knowledge_base.db
```

Docker Compose 中配置 PostgreSQL：

```
postgresql+psycopg://postgres:postgres@postgres:5432/test_knowledge_base
```

### 7.2 数据库初始化

应用启动时通过 `Base.metadata.create_all(bind=engine)` 自动创建所有表，无需手动迁移。随后依次执行：
- `ensure_requirements_versioning_columns(engine)` — 补充需求版本化字段（`version`、`requirement_group_id` 及索引）
- `ensure_test_cases_precondition_column(engine)` — 补充测试用例 `precondition` 字段

确保已有数据库兼容新版本。同时自动创建 `uploads/` 目录用于文件存储，并通过 `StaticFiles` 挂载 `/uploads` 路径提供静态文件访问。

### 7.3 Session 管理

使用 FastAPI 的 `Depends(get_db)` 注入 SQLAlchemy Session，每次请求获取一个新 Session，请求结束后自动关闭。

---

## 8. 开发指南

### 8.1 本地开发

**启动后端：**
```bash
cd backend
# 推荐：使用项目内已验证的 Python 3.8 虚拟环境（可直接复用）
source .venv/bin/activate

# 若首次创建 .venv（系统 python3=3.8）
# python3 -m venv .venv
# .venv/bin/python -m pip install -i https://pypi.org/simple --upgrade pip setuptools wheel

pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

> 说明：当前 LLM 调用不依赖 `zai-sdk`；OpenAI provider 依赖 `openai` SDK，智谱 provider 走 `httpx` SSE 通道。
> 若本机存在 pyenv/shims 或 shell hash 污染，建议直接使用 `./.venv/bin/python -m uvicorn ...` 启动，避免误用系统 Python 导致 `No module named uvicorn`。

**启动前端：**
```bash
cd frontend
npm install
npm run dev
```

**访问地址：**
- 前端：`http://localhost:5173`
- 后端 API：`http://localhost:8000`
- Swagger 文档：`http://localhost:8000/docs`

### 8.2 Docker 一键启动

```bash
docker compose up --build
```

服务编排：
- `testkb-postgres` — PostgreSQL 15 数据库 (端口 5432)
- `testkb-backend` — FastAPI 后端 (端口 8000)
- `testkb-frontend` — Vite 前端 (端口 5173)

### 8.3 运行测试

```bash
pytest backend/tests -q
```

**测试覆盖范围：**
- `test_ai_parser.py` — AI 解析单测（覆盖 LLM 成功、LLM 失败降级、`decision_tree` 形态兼容）
- `test_rule_engine.py` — 规则路径推导的正确性 (DFS 算法) + 环场景保护回归
- `test_coverage_and_impact.py` — 覆盖率计算 & 影响分析标记逻辑
- `test_api_smoke.py` — 全链路 API 冒烟测试 (项目→需求→规则→用例→覆盖矩阵→AI解析)；含回归用例：删除节点后规则树与覆盖矩阵不再返回该节点、更新 parent 时环检测返回 400
- `test_architecture_analyzer.py` — 需求拆解分析引擎单测 + 全链路 API 测试 (覆盖仅流程图分析、图文联合分析、分析→查看→导入→验证规则树；含包裹层 + 别名字段归一化回归)
- `test_base_llm_client.py` — LLM 基类测试（`seed` 参数按配置透传/缺省不透传）
- `test_openai_client.py` — OpenAI 客户端单测（请求格式、`json_object`、vision 请求）
- `test_fallback_llm.py` — 多模型回退链路测试（优先级、回退、双失败）
- `test_llm_client.py` — LLM 包装器测试（环境变量驱动组链、调用委托）
- `scripts/check_openai_call.py` — OpenAI 连通性脚本（同时校验 `OPENAI_BASE_URL` SDK 调用与 `OPENAI_API_URL` 直连调用）
- `test_projects_crud_api.py` — 项目 & 需求完整 CRUD API 测试 (创建→查看→更新→删除→404 验证)
- `test_recommender.py` — 风险权重计算、覆盖集合计算、贪心推荐算法正确性 + 推荐 API 冒烟测试
- `test_testcases_api.py` — 测试用例 CRUD API 测试 (创建→查看→更新→删除) + 按需求 ID 筛选用例、更新绑定关系验证、`status` 字段创建/更新回归验证
- `conftest.py` — `autouse` 数据库重建 fixture（`drop_all + create_all`），避免跨测试数据污染

### 8.4 环境变量

**后端 (`backend/.env.example`):**

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| DATABASE_URL | sqlite:///./test_knowledge_base.db | 数据库连接串 |
| ANALYZER_PROVIDER | mock | 需求拆解分析引擎 (`mock` 或 `llm`) |
| AI_PARSE_PROVIDER | llm | 规则树 AI 解析引擎（`llm` / `auto` / `mock`） |
| OPENAI_API_KEY | (空) | OpenAI API Key（配置后作为首选 provider） |
| OPENAI_BASE_URL | https://api.openai.com/v1 | OpenAI SDK 基础地址（支持第三方网关，如 `https://api.routin.ai/v1`） |
| OPENAI_API_URL | https://api.openai.com/v1/chat/completions | OpenAI Chat Completions 接口地址（兼容脚本直连校验） |
| OPENAI_TEXT_MODEL | gpt-4o | OpenAI 文本模型 |
| OPENAI_VISION_MODEL | gpt-4o | OpenAI 多模态模型 |
| ZHIPU_API_KEY | your-zhipu-api-key-here | 智谱 API Key（`llm` 模式必填） |
| ZHIPU_API_URL | https://open.bigmodel.cn/api/paas/v4/chat/completions | 智谱 Chat Completions SSE 接口地址 |
| ZHIPU_VISION_MODEL | glm-4.7 | 多模态阶段模型 |
| ZHIPU_TEXT_MODEL | glm-4.7 | 结构化生成阶段模型 |
| LLM_CONNECT_TIMEOUT | 10 | LLM 建连超时（秒） |
| LLM_REQUEST_TIMEOUT | 60 | LLM 请求超时时间（秒） |
| LLM_MAX_RETRIES | 2 | LLM 请求失败重试次数 |
| LLM_THINKING_TYPE | disabled | `thinking` 参数开关类型 |
| LLM_MAX_TOKENS | 6000 | 最大输出 token |
| LLM_TEMPERATURE | 0.15 | 采样温度（结构化输出建议低温） |
| LLM_SEED | 42 | 采样随机种子（配置后提升同输入可复现性） |

**LLM JSON 模式建议：**
- 多模型链路默认使用 `response_format=json_object`，确保 OpenAI 与智谱回退行为一致。
- 当使用 `LLMClient.chat_with_json` 进行结构化 JSON 生成时，建议保持 `LLM_THINKING_TYPE=disabled`（已为默认值）。
- 原因：在 `glm-4.7 + response_format=json_object + thinking=enabled` 组合下，模型可能只返回 `reasoning_content` 且 `content` 为空，导致 JSON 解析失败。
- 建议将 `.env`（本地）设置为：
  - `ANALYZER_PROVIDER=llm`
  - `AI_PARSE_PROVIDER=llm`
  - `OPENAI_API_KEY=<your-openai-key>`（可选但推荐，作为主链 provider）
  - `OPENAI_BASE_URL=<your-openai-base-url>`（可选；使用第三方网关时必填，如 `https://api.routin.ai/v1`）
  - `ZHIPU_API_KEY=<your-zhipu-key>`（可选，作为回退 provider）
  - `LLM_THINKING_TYPE=disabled`

**前端 (`frontend/.env.example`):**

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| VITE_API_BASE_URL | http://localhost:8000 | 后端 API 地址 |

---

## 9. 代码分层与职责

### 后端三层架构

```
API 路由层 (app/api/)
  ├── 接收 HTTP 请求，参数校验 (Pydantic)
  ├── 调用 Service 层处理业务
  └── 返回响应

Service 业务层 (app/services/)
  ├── rule_engine — 规则路径推导
  ├── coverage — 覆盖率计算
  ├── impact — 变更影响分析
  ├── risk_scorer — 风险权重计算
  ├── cover_set — 用例覆盖集合计算
  ├── recommender — 贪心推荐算法
  ├── impact_domain — CHANGE 模式影响域计算
  ├── ai_parser — AI 需求解析
  ├── architecture_analyzer — 需求拆解 (Provider 模式)
  └── test_plan_generator — 测试方案与用例生成 (LLM 两阶段)

Model 数据层 (app/models/ + app/core/)
  ├── entities — SQLAlchemy 实体定义
  └── database — 连接 & Session
```

### 前端分层

```
Pages (页面组件)
  ├── 页面级组件，组合 UI 与业务逻辑
  └── 各页面独立文件夹

API 层 (api/)
  ├── 对后端 REST API 的 TypeScript 封装
  ├── 默认使用 Axios 实例 (baseURL + 15s 超时)
  ├── 需求拆解分析接口单独覆盖超时为 120s（避免 LLM 慢请求被前端提前中断）
  ├── projects — CRUD (create/list/get/update/delete) 项目 & 需求
  ├── testcases — CRUD (create/list/get/update/delete) 测试用例 + 需求筛选
  ├── rules — 规则树 CRUD + AI 解析 + 影响预览
  ├── coverage — 覆盖矩阵查询
  ├── recommendation — 回归推荐执行 + 历史查询
  ├── architecture — 需求拆解分析/查看/导入
  └── testPlan — 测试方案生成/用例生成/确认导入/会话管理

Store (stores/)
  └── Zustand 全局状态管理 (切换项目时自动清空已选需求)

Types (types/)
  └── 所有 TypeScript 类型/接口定义

Utils (utils/)
  └── enumLabels — 枚举值中文标签映射 & 安全获取函数
```

---

## 10. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| ORM | SQLAlchemy 2.x | 成熟稳定，声明式模型定义，支持多种数据库 |
| 状态管理 | Zustand | 相比 Redux 更轻量，API 简洁，足够 MVP 规模 |
| 树可视化 | simple-mind-map | 思维导图体验更贴近 XMind；支持拖拽改层级、聚焦高亮、适应画布与多格式导出 |
| 规则路径 | 自动派生 | 节点变更时自动 DFS 重算，避免手动维护路径的不一致 |
| 节点删除 | 软删除 (status=deleted) | 保留历史数据，不破坏路径和绑定关系 |
| 影响分析 | 节点级直接关联 | MVP 阶段按节点绑定关系直接标记，后续可扩展路径级分析 |
| 数据库 | SQLite 本地 / PostgreSQL 生产 | 开发零配置，生产环境仅需切换 DATABASE_URL |
| AI 解析 | LLM 优先 + 规则分句兜底 | 兼顾产出质量与稳定性，失败可自动降级 |
| 需求拆解引擎 | Provider 模式 | 抽象基类 + 具体实现，便于后续接入 LLM/多模型切换 |
| 文件上传 | 本地磁盘 + 静态挂载 | MVP 阶段简单可靠，后续可迁移到对象存储 |
| Markdown 渲染 | react-markdown | 测试方案以 Markdown 生成，前端直接渲染，灵活度高 |
| 需求版本化 | requirement_group_id + version 字段 | 同一需求的多个版本共享 group_id，规则树按版本隔离，互不干扰 |
| 规则树 Diff | LLM 语义 + 算法兜底 | LLM 提供可读性更强的语义摘要；算法确保 100% 可用 |
| 会话式 AI 生成 | 多轮消息持久化 + 快照 | 保留完整交互历史和每步树快照，支持回溯与审计 |
| 测试方案生成 | 两阶段 LLM（方案 → 用例） | 先生成方案再生成用例，每阶段可人工审查编辑，兼顾质量与可控性 |
| Schema 迁移 | 启动时 ALTER TABLE 补列 | 避免引入 Alembic 的额外复杂度，适合当前阶段 |

---

## 11. 未来演进方向

| 方向 | 说明 |
|------|------|
| **P1+ (已实现)** | ~~需求版本化~~ — 已支持创建新版本、版本列表查看、规则树按版本隔离 |
| **P1+ (已实现)** | ~~规则树版本 Diff~~ — LLM 语义级对比 + 算法兜底 |
| **P1+ (已实现)** | ~~规则树会话式 AI 生成~~ — 多轮对话生成/审查/增量更新/确认导入 |
| **P1+ (已实现)** | ~~风险识别分析~~ — AI 识别规则树风险、逐条决策、转为节点、删除风险项 |
| **P1+ (已实现)** | ~~测试方案与用例生成~~ — AI 两阶段生成测试方案和用例、会话管理、确认导入 |
| **P2: LLM 能力增强** | 在已接入 LLM 的基础上优化 Prompt、引入缓存/观测与质量评估，提升结构化输出稳定性 |
| **P2: 架构分析历史管理** | 分析记录列表、对比、重新分析 |
| **P2: 版本回滚** | 支持将需求回退到历史版本（当前仅支持创建新版本和版本对比） |
| **P2: 批量操作** | 支持批量导入/导出规则和用例 |
| **P2: 权限与协作** | 多用户角色、权限控制、操作审计日志 |
| **P2: 数据库迁移** | 引入 Alembic 进行 schema 版本管理 |
| **P2: 文件存储升级** | 从本地磁盘迁移到对象存储 (S3/OSS) |
| **P3: 执行结果关联** | 对接 CI/CD，自动采集测试执行结果 |
| **P3: 可视化增强** | 覆盖热力图、路径高亮、节点搜索 |

---

## 12. 版本更新记录（按日期）

### 12.1 记录模板

> 每次功能、接口、数据模型、页面交互有改动时，按以下模板追加一条记录（新记录放最上方）。

```markdown
### YYYY-MM-DD — <版本主题>

**范围：**
- 后端 / 前端 / 文档 / 测试（可多选）

**改动摘要：**
- <要点 1>
- <要点 2>
- <要点 3>

**涉及文件：**
- `path/to/file_a`
- `path/to/file_b`

**接口/模型变更：**
- API: `<METHOD> <PATH>`（新增/变更/废弃）
- Model: `<实体或字段>`（新增/变更）

**验证记录：**
- `命令`: <例如 `pytest -q` / `npm run build`>
- `结果`: <通过/失败 + 关键结论>

**兼容性说明：**
- <是否影响旧接口/旧页面行为；是否需要数据迁移>
```

### 12.2 更新日志

#### 2026-03-09 — 风险识别超时误报与重复生成修复

**范围：**
- 后端 / 前端 / 文档

**改动摘要：**
- **前端长超时修复**：`frontend/src/api/risks.ts` 中的风险分析请求改为单独使用 `180000ms` 超时，不再复用 Axios 全局 `15s` 超时，避免 LLM 实际仍在处理时页面先提示"风险分析失败"
- **后端并发合并**：`backend/app/services/risk_service.py` 新增按 `requirement_id` 维度的分析中状态管理；同一需求已有分析进行时，重复点击只会等待首个请求完成，不会再触发额外 LLM 调用
- **风险结果覆盖写入**：风险重新分析时改为先清空该需求下旧风险记录，再写入新结果，避免因超时重试或重复点击造成风险列表出现多轮重复记录
- **回归测试补齐**：新增 `backend/tests/test_risk_service.py`，验证并发双击场景下只调用一次 LLM，且数据库最终仅保留一份风险结果

**涉及文件：**
- `backend/app/services/risk_service.py`
- `backend/tests/test_risk_service.py` (新增)
- `frontend/src/api/risks.ts`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无新增接口；`POST /api/ai/risks/analyze` 的调用语义补充为"同需求并发请求合并，返回最新快照"
- Model: 无

**验证记录：**
- `命令`: `pytest backend/tests/test_risk_service.py -q`
- `结果`: 通过（`1 passed`）
- `命令`: `cd frontend && npm run build`
- `结果`: 通过（保留既有第三方 `'use client'` 指令忽略与 chunk size 警告，不影响本次修复）

**兼容性说明：**
- 不涉及数据库迁移
- 不改变风险项决策/转节点/删除接口形态
- 单进程部署下可直接避免重复 LLM 调用；若未来切换多进程/多实例部署，仍建议补充数据库级或任务队列级幂等控制

#### 2026-03-07 — 规则树测试方案支持 Markdown 导出/导入

**范围：**
- 前端 / 文档

**改动摘要：**
- **规则树 Markdown 导出**：规则树页导出菜单新增 `Markdown` 选项，可将当前规则树导出为 Markdown 文本，便于离线编写或人工整理测试方案
- **测试方案 Markdown 导入**：测试方案抽屉第一步新增 `.md` 文件导入入口，导入后自动创建 `TestPlanSession`、写入 `plan_markdown`，并直接进入方案审核编辑态
- **空测试点可继续生成**：当当前方案没有结构化测试点时，审核页改为展示信息提示而不是直接隐藏区域，允许用户手动补点，或直接基于 Markdown 方案继续生成测试用例

**涉及文件：**
- `frontend/src/pages/RuleTree/index.tsx`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无
- Model: 无

**验证记录：**
- `命令`: `cd frontend && npm run build`
- `结果`: 通过（存在既有第三方 `'use client'` 指令忽略与 chunk size 警告，不影响本次功能）

#### 2026-03-06 — 测试方案与用例 AI 生成 + 风险删除 + 用例前置条件字段

**范围：**
- 后端 / 前端

**改动摘要：**
- **测试方案与用例生成（新功能）**：新增 `TestPlanSession` 数据模型和 `/api/test-plan` 系列接口，支持 AI 两阶段生成（先生成测试方案 Markdown + 测试点列表，再基于方案生成结构化测试用例）；生成后自动校验节点覆盖率，未覆盖的可测试节点自动补充兜底测试点/用例；支持会话管理（创建/归档/历史回溯）和确认导入到用例库
- **风险项删除**：新增 `DELETE /api/rules/risks/{risk_id}` 接口，支持物理删除风险项；前端 RiskPanel 每条风险项新增「删除」按钮，通过 Popconfirm 二次确认后执行
- **用例前置条件字段**：`TestCase` 模型新增 `precondition` 字段（Text，可选），用于存储测试用例的前置条件；新增 `ensure_test_cases_precondition_column` 迁移函数，启动时自动补列
- **测试方案生成 Prompt**：新增 `backend/app/services/prompts/test_plan.py`，包含方案生成和用例生成两组 Prompt 模板，严格约束输出格式并禁止编造规则树未描述的系统功能

**涉及文件：**
- `backend/app/api/test_plan.py` (新增)
- `backend/app/schemas/test_plan.py` (新增)
- `backend/app/services/test_plan_generator.py` (新增)
- `backend/app/services/prompts/test_plan.py` (新增)
- `backend/app/models/entities.py`
- `backend/app/main.py`
- `backend/app/core/schema_migrations.py`
- `backend/app/api/risks.py`
- `backend/app/services/risk_service.py`
- `backend/app/schemas/testcase.py`
- `frontend/src/api/testPlan.ts` (新增)
- `frontend/src/api/risks.ts`
- `frontend/src/types/index.ts`
- `frontend/src/pages/RuleTree/RiskPanel.tsx`

**接口/模型变更：**
- API: `GET /api/test-plan/sessions?requirement_id=N` (新增)
- API: `GET /api/test-plan/sessions/{session_id}` (新增)
- API: `POST /api/test-plan/sessions` (新增)
- API: `PUT /api/test-plan/sessions/{session_id}/archive` (新增)
- API: `PUT /api/test-plan/sessions/{session_id}/plan` (新增)
- API: `PUT /api/test-plan/sessions/{session_id}/cases` (新增)
- API: `POST /api/test-plan/generate` (新增)
- API: `POST /api/test-plan/generate-cases` (新增)
- API: `POST /api/test-plan/confirm-cases` (新增)
- API: `DELETE /api/rules/risks/{risk_id}` (新增)
- Model: `TestPlanSession` (新增表 `test_plan_sessions`)
- Model: `TestPlanSessionStatus` (新增枚举)
- Model: `TestCase` 新增 `precondition` (Text, nullable, default='') 字段
- Schema: `TestCaseCreate` / `TestCaseRead` / `TestCaseUpdate` 新增 `precondition` 字段

**兼容性说明：**
- `TestCase.precondition` 为可选字段，默认空字符串，已有数据无需手动迁移（启动时自动 ALTER TABLE）
- `TestPlanSession` 表通过 `create_all` 自动创建，无需手动迁移
- 新增 API 均为增量接口，不影响已有接口行为
- 风险删除为新增接口，不影响已有的接受/忽略/转节点功能

---

#### 2026-03-06 — 规则树交互增强（右键菜单/Diff 历史持久化/风险面板优化）

**范围：**
- 后端 / 前端

**改动摘要：**
- **Diff 历史持久化**：新增 `DiffRecord` 数据模型，版本对比结果自动保存；新增 3 个 API（历史列表/详情/删除）；版本对比弹窗新增「历史记录」Tab，支持查看和删除历史对比
- **右键上下文菜单**：规则树节点左键点击改为仅选中聚焦，右键点击弹出上下文菜单（编辑 / 新增子节点 / 删除），替代原来左键直接打开编辑抽屉的行为；画布顶部新增"右键节点可编辑"提示
- **MindMapWrapper 稳定性增强**：新增 `pendingDataRef` 队列机制，当 `setData` 正在执行时将后续数据排队等待，解决并发调用竞态条件
- **风险面板改进**：存在待处理风险项时禁用分析按钮并提示；新增 `onRisksChange` 回调同步父组件风险状态；滚动区域使用绝对定位修复溢出问题；折叠面板改为受控模式
- **需求列表版本列**：项目需求表格新增"版本"列，以 Tag `vN` 形式展示
- **并行加载优化**：规则树与风险数据改为 `Promise.all` 并行加载，减少页面初始化等待
- **会话快照恢复**：会话消息历史中 AI 生成的消息支持「应用此版本到规则树」操作
- **DiffResultDisplay 组件抽取**：将 Diff 结果展示逻辑提取为独立组件，在"新对比"和"历史记录"中复用
- **Literal 导入兼容**：`risk.py` 将 `Literal` 从 `typing_extensions` 导入，兼容 Python 3.7

**涉及文件：**
- `backend/app/api/tree_diff.py`
- `backend/app/models/entities.py`
- `backend/app/schemas/risk.py`
- `backend/app/schemas/tree_diff.py`
- `frontend/src/api/treeDiff.ts`
- `frontend/src/pages/ProjectList/index.tsx`
- `frontend/src/pages/RuleTree/MindMapWrapper.tsx`
- `frontend/src/pages/RuleTree/RiskPanel.tsx`
- `frontend/src/pages/RuleTree/index.tsx`
- `frontend/src/types/index.ts`

**接口/模型变更：**
- API: `GET /api/rules/diff/history?project_id=N&requirement_group_id=M` (新增)
- API: `GET /api/rules/diff/history/{record_id}` (新增)
- API: `DELETE /api/rules/diff/history/{record_id}` (新增)
- API: `GET /api/rules/diff` 行为增强 — 执行对比后自动保存 `DiffRecord`
- Model: `DiffRecord` (新增表 `diff_records`)
- Schema: `DiffRecordRead` (新增)
- Type: `DiffRecordRead` (前端类型新增)

**兼容性说明：**
- 新增 API 均为增量接口，不影响已有接口行为
- `DiffRecord` 表通过 `create_all` 自动创建，无需手动迁移
- Diff 结果保存失败不影响 Diff 接口正常返回（try-except 保护）
- 前端规则树交互变更：左键不再直接打开编辑抽屉，改为右键上下文菜单

---

#### 2026-03-07 — 规则树版本 Diff 可读性增强

**范围：**
- 后端 / 前端 / 文档

**改动摘要：**
- `FlowChange` 结构增强：新增 `title`、`before`、`after`、`test_suggestion`，让 Diff 结果直接表达“旧版怎么做 / 新版怎么做 / 建议怎么测”
- `SemanticDiffResult` 增加 `key_changes` 与结构化 `risks`，用于在摘要区快速浏览核心变化，并在风险区展示可执行验证建议
- 规则树版本 Diff 的 LLM Prompt 改为更偏业务沟通的输出约束，明确禁止抽象术语和技术标识符，减少“看不懂改了什么”的结果
- 规则树页 Diff 弹窗同步升级：摘要区支持关键变化列表，风险区支持结构化风险卡片，流程变更表支持旧/新对照与展开查看测试建议

**涉及文件：**
- `backend/app/schemas/tree_diff.py`
- `backend/app/services/tree_diff.py`
- `frontend/src/types/index.ts`
- `frontend/src/pages/RuleTree/index.tsx`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- Schema: `FlowChange` 新增 `title?: string | null`
- Schema: `FlowChange` 新增 `before?: string | null`
- Schema: `FlowChange` 新增 `after?: string | null`
- Schema: `FlowChange` 新增 `test_suggestion?: string | null`
- Schema: 新增 `RiskNote { risk, suggestion }`
- Schema: `SemanticDiffResult` 新增 `key_changes?: string[] | null`
- Schema: `SemanticDiffResult` 新增 `risks?: RiskNote[] | null`
- Schema: `SemanticDiffResult` 保留 `risk_notes?: string | null` 作为兼容字段
- Type: `frontend/src/types/index.ts` 与后端 Diff Schema 同步
- API: `GET /api/rules/diff` 返回体增强，但保持增量兼容

**验证记录：**
- `cd backend && ./.venv/bin/python -c "from app.schemas.tree_diff import SemanticDiffResult, FlowChange, RiskNote; import app.services.tree_diff as tree_diff; print('backend diff import ok')"`：通过
- `cd frontend && npm run build`：通过（存在既有第三方 `'use client'` 与 chunk size 警告，不影响本次变更）

---

#### 2026-03-06 — 需求版本化 + 规则树版本 Diff + 会话式 AI 生成 + 风险识别分析

**范围：**
- 后端 / 前端 / 文档

**改动摘要：**
- **需求版本化**：`Requirement` 模型新增 `version`、`requirement_group_id` 字段；新增创建新版本 (`POST .../new-version`) 和版本列表 (`GET .../versions`) 接口；前端规则树页增加版本选择器和创建新版本按钮，旧版本自动进入只读模式
- **规则树版本 Diff**：新增 `GET /api/rules/diff` 接口，优先使用 LLM 语义级对比（输出变更摘要 + 流程级变更列表），失败自动回退算法 Diff（基于 SequenceMatcher 模糊匹配）；前端弹窗展示 Diff 结果
- **规则树会话式 AI 生成**：新增 `/api/rules/sessions` 系列接口（创建/列表/详情/生成/更新/确认），支持多轮对话式规则树生成 → AI 自动审查 → 增量更新 → 确认导入正式库；消息和树快照完整持久化
- **风险识别分析**：新增 `POST /api/risks/analyze` 接口，基于需求文本和规则树通过 LLM 识别潜在风险；前端 RiskPanel 组件支持逐条决策（接受/忽略/转节点）
- **LLM Client 增强**：`LLMClient` 新增 `chat_with_messages` 方法，支持通用消息列表调用，兼容多 provider 回退机制
- **Schema 迁移**：新增 `schema_migrations.py`，启动时自动补充 `version`、`requirement_group_id` 列和索引，确保已有数据库兼容
- **前端错误处理增强**：`client.ts` 新增 `getErrorMessage` 工具函数，统一 Axios 错误消息提取
- **Python 3.12 兼容**：`main.py` 增加 `_patch_forwardref_evaluate_for_python_312` 补丁

**涉及文件：**
- `backend/app/models/entities.py`
- `backend/app/main.py`
- `backend/app/core/schema_migrations.py` (新增)
- `backend/app/api/projects.py`
- `backend/app/api/tree_diff.py` (新增)
- `backend/app/api/rule_tree_session.py` (新增)
- `backend/app/api/risks.py` (新增)
- `backend/app/schemas/project.py`
- `backend/app/schemas/tree_diff.py` (新增)
- `backend/app/schemas/rule_tree_session.py` (新增)
- `backend/app/schemas/risk.py` (新增)
- `backend/app/services/tree_diff.py` (新增)
- `backend/app/services/rule_tree_session.py` (新增)
- `backend/app/services/risk_service.py` (新增)
- `backend/app/services/prompts/rule_tree_session.py` (新增)
- `backend/app/services/prompts/risk_analysis.py` (新增)
- `backend/app/services/llm_client.py`
- `backend/app/services/base_llm_client.py`
- `backend/app/services/fallback_llm_client.py`
- `frontend/src/types/index.ts`
- `frontend/src/api/client.ts`
- `frontend/src/api/projects.ts`
- `frontend/src/api/treeDiff.ts` (新增)
- `frontend/src/api/ruleTreeSession.ts` (新增)
- `frontend/src/api/risks.ts` (新增)
- `frontend/src/pages/RuleTree/index.tsx`
- `frontend/src/pages/RuleTree/RiskPanel.tsx` (新增)
- `frontend/src/pages/RuleTree/dataAdapter.ts`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: `POST /api/projects/{pid}/requirements/{rid}/new-version` (新增)
- API: `GET /api/projects/{pid}/requirements/{rid}/versions` (新增)
- API: `GET /api/rules/diff?old_requirement_id=N&new_requirement_id=M` (新增)
- API: `POST /api/rules/sessions` (新增)
- API: `GET /api/rules/sessions?requirement_id=N` (新增)
- API: `GET /api/rules/sessions/{sid}` (新增)
- API: `POST /api/rules/sessions/{sid}/generate` (新增)
- API: `POST /api/rules/sessions/{sid}/update` (新增)
- API: `POST /api/rules/sessions/{sid}/confirm` (新增)
- API: `POST /api/risks/analyze` (新增)
- Model: `Requirement` 新增 `version` (Integer, default=1)、`requirement_group_id` (Integer, nullable) 字段
- Model: `RuleTreeSession` (新增表 `rule_tree_sessions`)
- Model: `RuleTreeMessage` (新增表 `rule_tree_messages`)
- Schema: `RequirementRead` 新增 `version`、`requirement_group_id` 字段
- Schema: `RequirementVersionRead` (新增)

**兼容性说明：**
- `Requirement` 新字段 `version` 默认值为 1、`requirement_group_id` 可为空，已有数据无需手动迁移（启动时自动 ALTER TABLE）
- 新增 API 均为增量接口，不影响已有接口行为
- 前端规则树页面整合了版本管理、会话 AI 和风险面板，原有功能（节点 CRUD、AI 解析、画布同步）保持不变

---

#### 2026-02-27 — 规则树 AI 解析切换为 LLM 优先并增加来源标识

**范围：**
- 后端 / 前端 / 文档 / 测试

**改动摘要：**
- `POST /api/ai/parse` 从“仅规则分句”升级为“LLM 优先 + 规则分句兜底”，返回 `analysis_mode` 标识本次解析来源
- `ai_parser` 新增 LLM 产物归一化与树结构修复，兼容 `decision_tree.nodes` / `decisionTree` 与常见别名字段（如 `nodeId/nodeType/parentId/text`）
- 规则树页“AI 半自动解析”弹窗新增解析引擎提示（`LLM` / `Mock（LLM降级）` / `Mock`），便于现场判断质量来源
- 新增回归测试覆盖：LLM 成功、LLM 失败降级、`decision_tree` 形态兼容；API 冒烟测试增加 `analysis_mode` 断言

**涉及文件：**
- `backend/app/services/ai_parser.py`
- `backend/tests/test_ai_parser.py`
- `backend/tests/test_api_smoke.py`
- `frontend/src/pages/RuleTree/index.tsx`
- `frontend/src/types/index.ts`
- `backend/.env.example`
- `docs/联调启动说明.md`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: `POST /api/ai/parse` 响应由 `{nodes}` 扩展为 `{analysis_mode, nodes}`
- Model: 无（数据库结构无变更）

**验证记录：**
- `命令`: `cd backend && ./.venv/bin/python -m pytest tests/test_ai_parser.py tests/test_api_smoke.py -k "ai_parse or test_parse_requirement_text" -q`
- `结果`: 通过（4 passed）
- `命令`: `cd frontend && npm run build`
- `结果`: 通过（构建成功，存在既有 `use client` 打包警告，不影响产物）

**兼容性说明：**
- 兼容旧前端：`nodes` 字段保持不变；新增字段 `analysis_mode` 为向后兼容扩展
- 无数据迁移需求

#### 2026-02-27 — 需求拆解 LLM 结构漂移兼容扩展（包裹层/别名字段/双重 JSON 编码）

**范围：**
- 后端 / 文档 / 测试

**改动摘要：**
- `LLMAnalyzerProvider` 的归一化能力扩展：支持从 `data/result/output/analysis/payload/response` 包裹层提取有效产物，支持 camelCase 与别名字段映射（如 `decisionTree/testPlan/riskPoints/testCases`）
- 细化节点/风险/用例字段兼容：支持 `nodeId/nodeType/risk/level/actions/expected/nodeIds` 等漂移字段，减少“可修复结构”误判为无效而触发 `mock_fallback`
- 降级可观测性增强：校验与归一化日志补充 `payload_summary`，保留 `raw_error/normalize_error`，便于快速定位失败层级
- `LLMClient` 增强 JSON 解析：新增双重 JSON 编码解码与恢复路径日志（raw parse 失败后提取对象、再做嵌套解码）
- 新增回归测试覆盖两类高频问题：包裹层+别名字段、双重 JSON 编码

**涉及文件：**
- `backend/app/services/architecture_analyzer.py`
- `backend/app/services/llm_client.py`
- `backend/tests/test_architecture_analyzer.py`
- `backend/tests/test_llm_client.py`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无（`/api/ai/architecture/*` 出参结构不变）
- Model: 无（数据库结构无变更）

**验证记录：**
- `命令`: `pytest -q backend/tests/test_architecture_analyzer.py`
- `结果`: 通过（10 passed）
- `命令`: `pytest -q backend/tests/test_llm_client.py`
- `结果`: 通过（5 passed）

**兼容性说明：**
- 对现有接口与前端无破坏性影响；仅增强“可恢复结构漂移”兼容能力，降低不必要的 `analysis_mode=mock_fallback` 触发概率

#### 2026-02-27 — 需求拆解 LLM 输出归一化与可观测性增强

**范围：**
- 后端 / 文档 / 测试

**改动摘要：**
- 在 `LLMAnalyzerProvider` 的“校验失败 -> 降级”之间新增归一化层：对常见 LLM 输出漂移（字段缺失、类型不一致）自动修正后再做二次校验
- 归一化覆盖高频问题：`test_plan.sections` 非字符串数组、`test_cases.steps` 为数组、`related_node_ids` 为字符串、`risk_points` 缺 `id/related_node_ids/mitigation`、风险等级中英文混用
- 增强 LLM 调用链日志：记录请求起始、重试、HTTP 非 200 响应摘要、SSE 空内容告警；降级日志补充 `raw_error` 与 `normalize_error`，便于快速定位是“调用失败”还是“结构失败”
- 本地联调启动建议更新：优先使用 `python -m uvicorn` 或 `./.venv/bin/python -m uvicorn`，避免 shim/系统 Python 导致 `No module named uvicorn`

**涉及文件：**
- `backend/app/services/architecture_analyzer.py`
- `backend/app/services/llm_client.py`
- `backend/tests/test_architecture_analyzer.py`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无（`/api/ai/architecture/*` 出参结构不变）
- Model: 无（数据库结构无变更）

**验证记录：**
- `命令`: `cd backend && .venv/bin/python -m pytest tests/test_architecture_analyzer.py -q -k "llm_analyzer"`
- `结果`: 通过（5 passed）
- `命令`: `cd backend && .venv/bin/python -m pytest tests/test_architecture_analyzer.py -q -k "normalizes_common_payload_shape_drifts or fallbacks_to_mock_on_invalid_llm_payload"`
- `结果`: 通过（2 passed）

**兼容性说明：**
- 对现有前端与接口无破坏性影响；当 LLM 输出仅存在“可修复漂移”时，将优先保持 `analysis_mode=llm`，减少不必要的 `mock_fallback`

#### 2026-02-27 — 需求拆解 LLM SSE 兼容性修复（`mock_fallback` 根因定位）

**范围：**
- 后端 / 文档 / 测试

**改动摘要：**
- 定位并确认“`Mock（LLM降级）`”的真实根因之一：`LLMClient` 在 SSE 读取时调用 `response.iter_lines(decode_unicode=True)`，与 `httpx==0.24.1` 不兼容
- 修复 `backend/app/services/llm_client.py` 的 SSE 解析逻辑：改为 `iter_lines()` 并统一处理 `bytes/str`，避免 `TypeError` 触发 LLM 全量降级
- 补充故障定位结论：在受限沙箱中还可能出现 DNS 解析失败（`Could not resolve host: open.bigmodel.cn`），会同样触发 `mock_fallback`

**涉及文件：**
- `backend/app/services/llm_client.py`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无
- Model: 无

**验证记录：**
- `命令`: `cd backend && set -a && source .env && set +a && .venv/bin/python - <<'PY' ... LLMClient.chat_with_json(...) ... PY`
- `结果`: 通过（返回 `LLM_OK {'ok': True}`）
- `命令`: `cd backend && source .venv/bin/activate && pytest -q tests/test_architecture_analyzer.py`
- `结果`: 通过（8 passed）

**兼容性说明：**
- 对现有接口与前端无破坏性影响；属于 SSE 读取层实现兼容修复

#### 2026-02-27 — 需求拆解引擎来源标识与超时兜底优化

**范围：**
- 前后端 / 文档 / 测试

**改动摘要：**
- 后端在需求拆解分析结果新增 `analysis_mode` 字段，并写入 `ArchitectureAnalysis.analysis_result` 持久化
- `analysis_mode` 支持三种值：`llm` / `mock` / `mock_fallback`
- 前端需求拆解页面新增“分析引擎”展示标签，可直观看到本次实际引擎来源
- 前端对需求拆解分析接口单独提高超时到 `120000ms`，避免默认 15s 超时导致“分析失败”误报
- 前端增加兜底：若后端未返回 `analysis_mode`，显示“未知”并提示重启后端

**涉及文件：**
- `backend/app/services/architecture_analyzer.py`
- `backend/app/api/architecture.py`
- `backend/app/schemas/architecture.py`
- `backend/tests/test_architecture_analyzer.py`
- `frontend/src/api/architecture.ts`
- `frontend/src/pages/ArchitectureAnalysis/index.tsx`
- `frontend/src/types/index.ts`
- `KNOWLEDGE_BASE.md`
- `docs/联调启动说明.md`

**接口/模型变更：**
- API: `POST /api/ai/architecture/analyze` 响应新增 `analysis_mode`
- API: `GET /api/ai/architecture/{analysis_id}` 的 `result` 内新增 `analysis_mode`
- Model: 无（数据库字段不变，仅 `analysis_result` JSON 结构扩展）

**验证记录：**
- `命令`: `pytest -q backend/tests/test_architecture_analyzer.py`
- `结果`: 通过（8 passed）
- `命令`: `npm run build`（frontend）
- `结果`: 通过（存在既有 Vite 打包告警，不影响本次变更）

**兼容性说明：**
- 旧前端可忽略新增字段继续工作；新前端在旧后端场景会显示“未知”并提示重启后端

#### 2026-02-27 — LLM 本地运行环境与连通性校准

**范围：**
- 后端 / 文档

**改动摘要：**
- 新增并验证项目内运行环境 `backend/.venv`（Python 3.8），用于稳定运行 `httpx + SSE` 调用链
- 本地连通性验证通过：SSE 直连 `glm-4.7` 返回成功，`LLMClient.chat_with_json` 在 `LLM_THINKING_TYPE=disabled` 下可稳定解析 JSON
- 补充 JSON 模式参数建议：结构化生成场景优先使用 `thinking=disabled`
- 更新 `.gitignore`，新增 `.venv/` 忽略规则，避免提交本地虚拟环境目录

**涉及文件：**
- `backend/.env`（本地）
- `.gitignore`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无
- Model: 无

**验证记录：**
- `命令`: `backend/.venv/bin/python -m pip install -i https://pypi.org/simple -r backend/requirements.txt`
- `结果`: 通过
- `命令`: `PYTHONPATH=backend backend/.venv/bin/python -c \"from app.services.llm_client import LLMClient; ...\"`（真实 API 调用）
- `结果`: 通过（返回 `{'status': 'ok'}`）
- `命令`: `PYTHONPATH=backend backend/.venv/bin/python -c \"from app.services.architecture_analyzer import LLMAnalyzerProvider; ...\"`
- `结果`: 通过（四产物返回，节点/用例/风险统计正常）

**兼容性说明：**
- 仅本地运行环境与配置建议更新，不影响现有 API 与数据库结构

#### 2026-02-27 — 回归推荐与用例详情交互缺陷修复

**范围：**
- 前端 / 文档

**改动摘要：**
- 修复回归推荐页跨需求筛选时“运行详情残留”问题：切换需求后清空旧详情，仅展示当前需求有效 run
- 增加回归推荐前置校验：当前需求无测试用例时禁止执行推荐并提示用户；用例加载中也会阻止触发
- 修复用例详情弹窗在长文本场景下的布局溢出：支持自动换行与纵向滚动，长节点/路径标签不再撑出弹窗

**涉及文件：**
- `frontend/src/pages/Recommendation/index.tsx`
- `frontend/src/pages/TestCases/index.tsx`
- `frontend/src/styles.css`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无
- Model: 无

**验证记录：**
- `命令`: `npm run build`（frontend）
- `结果`: 通过（存在既有 Vite 打包告警，不影响本次行为修复）
- `命令`: `npm test`（frontend）
- `结果`: 失败，原因是项目未配置 `test` script（`Missing script: "test"`）

**兼容性说明：**
- 不涉及后端接口和数据库结构变更；仅前端交互与展示层优化

#### 2026-02-27 — 需求拆解 LLM 通道切换（SSE Only）

**范围：**
- 后端 / 文档 / 测试

**改动摘要：**
- `LLMAnalyzerProvider` 从占位实现升级为可用实现：支持两阶段分析（多模态理解 + JSON 结构化生成）
- `LLMClient` 切换为纯 SSE（`httpx + text/event-stream`）实现，不再依赖 `zai-sdk`
- 新增 Prompt 模板管理与结果校验兜底机制（校验失败自动回退 `MockAnalyzerProvider`）
- 更新 `test_llm_client.py`，锁定 SSE 行为（流式拼接、JSON 提取、HTTP 错误、参数透传）

**涉及文件：**
- `backend/app/services/llm_client.py`
- `backend/app/services/prompts/architecture.py`
- `backend/app/services/architecture_analyzer.py`
- `backend/tests/test_llm_client.py`
- `backend/tests/test_architecture_analyzer.py`
- `backend/requirements.txt`
- `backend/.env.example`
- `README.md`

**接口/模型变更：**
- API: 无（`/api/ai/architecture/*` 出参与返回结构保持不变）
- Model: 无（数据库结构无变更）

**验证记录：**
- `命令`: `backend/.venv38/bin/python -m pytest backend/tests/test_llm_client.py backend/tests/test_architecture_analyzer.py -q`
- `结果`: 通过（12 passed）

**兼容性说明：**
- 接口层完全兼容；仅实现层由占位逻辑切换为真实 LLM 调用
- 若未配置 `ZHIPU_API_KEY` 或调用失败，`llm` 模式会自动回退到 `MockAnalyzerProvider`

#### 2026-02-26 — 回归参数术语统一（预算K → 回归K）

**范围：**
- 前端 / 文档

**改动摘要：**
- 将回归推荐页面参数文案从“预算(K)”统一为“回归K”
- 将运行详情文案从“预算 K”统一为“回归K”
- 同步更新知识库与实现计划中的相关术语描述，避免“预算”被理解为金额

**涉及文件：**
- `frontend/src/pages/Recommendation/index.tsx`
- `KNOWLEDGE_BASE.md`
- `docs/plans/回归推荐算法层_0e1588d8.plan.md`

**接口/模型变更：**
- API: 无
- Model: 无（字段名仍为 `k`，仅文案调整）

**验证记录：**
- `命令`: `rg -n '回归K' KNOWLEDGE_BASE.md docs/plans/回归推荐算法层_0e1588d8.plan.md frontend/src/pages/Recommendation/index.tsx`
- `结果`: 已命中文档与页面核心文案；旧术语仅保留在本条更新说明中用于变更解释

**兼容性说明：**
- 不影响接口与数据库结构，仅展示文案和文档术语更新

#### 2026-02-26 — 回归推荐算法层 + 前端联动

**范围：**
- 后端 / 前端 / 文档 / 测试

**改动摘要：**
- 新增回归推荐算法链路：风险评分、覆盖集合、贪心推荐、影响域计算，支持 `FULL/CHANGE` 两种模式
- 新增推荐运行落库实体 `RecoRun`、推荐结果实体 `RecoResult`，并开放推荐执行与历史查询 API
- 前端新增“回归推荐”页面，支持执行推荐、查看历史详情、从推荐结果一键跳转到用例管理并高亮目标用例
- 规则树新增父链环检测；路径推导 DFS 增加环保护，避免环结构导致递归溢出

**涉及文件：**
- `backend/app/api/recommendation.py`
- `backend/app/schemas/recommendation.py`
- `backend/app/models/entities.py`
- `backend/app/services/risk_scorer.py`
- `backend/app/services/cover_set.py`
- `backend/app/services/recommender.py`
- `backend/app/services/impact_domain.py`
- `backend/app/services/rule_engine.py`
- `backend/app/api/rules.py`
- `frontend/src/pages/Recommendation/index.tsx`
- `frontend/src/api/recommendation.ts`
- `frontend/src/pages/TestCases/index.tsx`
- `frontend/src/App.tsx`
- `frontend/src/types/index.ts`

**接口/模型变更：**
- API（新增）: `POST /api/reco/regression`、`GET /api/reco/runs`、`GET /api/reco/runs/{run_id}`
- Model（新增）: `RecoRun`、`RecoResult`
- API（行为增强）: `PUT /api/rules/nodes/{node_id}` 新增父链环检测

**验证记录：**
- `python3 -m pytest -q`（backend）: 通过，26 passed
- `npm run build`（frontend）: 通过（存在第三方依赖告警，不影响功能）

**兼容性说明：**
- 对旧接口保持兼容；新增推荐接口为增量能力
- SQLite 使用 `Base.metadata.create_all` 自动补表，无需手动迁移脚本

#### 2026-02-25 — 需求拆解能力增强

**范围：**
- 后端 / 前端 / 测试 / 文档

**改动摘要：**
- 支持流程图与文字描述的灵活输入（仅图 / 仅文 / 图文联合）
- 架构分析结果支持四产物展示与选择性导入
- 前端上传流程图文件读取兼容性修复（`originFileObj` 与原始 `File`）

**兼容性说明：**
- 原有流程保持兼容，属于能力增强

#### 2026-03-01 — 测试用例智能导入（Excel/XMind + LLM 匹配）

**范围：**
- 后端 / 前端 / 测试 / 文档

**改动摘要：**
- 新增测试用例导入后端能力：支持 `.xlsx/.xlsm/.xmind` 文件解析、LLM 批量匹配规则节点、关键词兜底匹配
- 新增导入 API：`/api/testcases/import/parse` 与 `/api/testcases/import/confirm`
- `confirm` 增加强校验与单事务：需求-项目归属校验、节点/路径归属校验、路径包含节点校验、未绑定用例禁止导入（仅可跳过）
- 前端 TestCases 页面新增三步导入向导（上传 -> 预览匹配 -> 确认导入），支持手动调整节点/路径、批量设置风险等级、未绑定行高亮

**新增/修改文件：**
- `backend/app/services/testcase_importer.py`
- `backend/app/services/testcase_matcher.py`
- `backend/app/services/prompts/testcase_match.py`
- `backend/app/api/testcase_import.py`
- `backend/app/schemas/testcase_import.py`
- `backend/tests/test_testcase_import_services.py`
- `backend/tests/test_testcase_import_api.py`
- `backend/app/main.py`
- `backend/requirements.txt`
- `frontend/src/api/testcases.ts`
- `frontend/src/types/index.ts`
- `frontend/src/pages/TestCases/index.tsx`
- `frontend/src/styles.css`

**接口变更：**
- `POST /api/testcases/import/parse` (multipart: `file`, `requirement_id`)
  - 返回解析预览、`confidence`、`match_reason`、`analysis_mode`
- `POST /api/testcases/import/confirm`
  - 返回 `imported_count / bound_count / skipped_count`
  - 关键错误码：`invalid_project_requirement_relation`、`unbound_case_not_allowed`、`invalid_bound_rule_node_ids`、`invalid_bound_path_ids`、`path_node_mismatch`

**验证记录：**
- `cd backend && pytest -q`：通过，50 passed
- `cd frontend && npm run build`：通过（存在既有第三方 `use client` 与 chunk size 警告，不影响功能）

#### 2026-03-01 — 用例删除级联与导入上传判空修复

**范围：**
- 后端 / 前端 / 测试 / 文档

**改动摘要：**
- 修复删除测试用例失败：当用例被 `reco_result` 引用时，删除接口不再触发 `NOT NULL constraint failed: reco_result.case_id`
- 模型层增加级联删除：`TestCase.reco_results` 配置 `cascade="all, delete-orphan"`，`RecoResult.case_id` 增加 `ondelete="CASCADE"`
- 新增回归测试：覆盖“推荐结果已落库后删除用例”的场景，确保 `DELETE /api/testcases/{case_id}` 返回 204 且推荐明细同步清理
- 修复用例智能导入上传判空误判：前端上传组件统一保留 `originFileObj`，并兼容读取 `UploadFile.originFileObj` 与原始 `File`

**涉及文件：**
- `backend/app/models/entities.py`
- `backend/tests/test_testcases_api.py`
- `frontend/src/pages/TestCases/index.tsx`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无新增接口；`DELETE /api/testcases/{case_id}` 删除行为增强（关联推荐明细自动清理）
- Model: `RecoResult.case_id` 外键补充 `ON DELETE CASCADE`；`TestCase.reco_results` 关系补充级联删除

**验证记录：**
- `backend/.venv/bin/python -m pytest backend/tests/test_testcases_api.py -q`：通过（5 passed）
- `npm --prefix frontend run build`：通过（存在既有第三方 `use client` 与 chunk size 警告，不影响功能）

#### 2026-03-01 — LLM 多模型回退机制（OpenAI 优先 + 智谱回退）与测试库隔离修复

**范围：**
- 后端 / 测试 / 文档

**改动摘要：**
- 将原单一智谱 `LLMClient` 重构为多模型回退链路：`OpenAIClient` 优先，失败自动回退 `ZhipuClient`，上层接口保持 `LLMClient()` 不变
- 抽取 `BaseLLMClient` 复用 SSE、重试、JSON 提取、图片 base64 能力；新增 `FallbackLLMClient` 做顺序回退编排与日志增强
- 新增 OpenAI 环境变量配置（`OPENAI_API_KEY/URL/TEXT_MODEL/VISION_MODEL`），阶段一统一使用 `response_format=json_object`
- 新增测试：`test_openai_client.py`、`test_fallback_llm.py`；更新 `test_llm_client.py` 适配包装器
- 修复测试隔离问题：`conftest.py` 新增 `autouse` 数据库重建 fixture，并清理 SQLite `-wal/-shm` 文件，消除跨用例唯一键冲突

**涉及文件：**
- `backend/app/services/base_llm_client.py`
- `backend/app/services/openai_client.py`
- `backend/app/services/zhipu_client.py`
- `backend/app/services/fallback_llm_client.py`
- `backend/app/services/llm_client.py`
- `backend/.env.example`
- `backend/tests/test_openai_client.py`
- `backend/tests/test_fallback_llm.py`
- `backend/tests/test_llm_client.py`
- `backend/tests/conftest.py`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无（上层 `LLMClient` 调用方式与接口出参保持兼容）
- Model: 无（数据库结构无变更）

**验证记录：**
- `cd backend && pytest -q`：通过，57 passed

**兼容性说明：**
- 现有 `from app.services.llm_client import LLMClient` 调用无需改造
- 当双模型都不可用时仍按既有逻辑回退到 Mock，保证功能可用性

#### 2026-03-01 — OpenAI SDK 网关接入与连通性脚本增强

**范围：**
- 后端 / 测试 / 文档

**改动摘要：**
- `OpenAIClient` 接入 `openai` SDK 调用链，支持通过 `OPENAI_BASE_URL` 对接第三方网关（例如 `https://api.routin.ai/v1`）
- 兼容已有 `OPENAI_API_URL`：当未设置 `OPENAI_BASE_URL` 时自动从 `OPENAI_API_URL` 反推 SDK 基础地址
- 新增/增强 `scripts/check_openai_call.py`：
  - 同时校验 `OPENAI_BASE_URL`（SDK 调用）与 `OPENAI_API_URL`（HTTP 直连调用）
  - `.env` 值作为脚本运行时优先配置，避免被当前 shell 中旧环境变量覆盖
  - 默认模型读取 `OPENAI_TEXT_MODEL`，未设置时默认 `gpt-5.3-codex`
- 新增依赖 `openai==1.51.2`，并更新 OpenAI 相关单测以覆盖 SDK 分支

**涉及文件：**
- `backend/app/services/openai_client.py`
- `backend/scripts/check_openai_call.py`
- `backend/tests/test_openai_client.py`
- `backend/requirements.txt`
- `backend/.env.example`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无
- Model: 无

**验证记录：**
- `cd backend && pytest -q tests/test_openai_client.py tests/test_llm_client.py tests/test_fallback_llm.py`：通过（12 passed）

**兼容性说明：**
- `LLMClient` 上层接口无变化，仍保持零侵入
- 网关场景建议优先配置 `OPENAI_BASE_URL`；保留 `OPENAI_API_URL` 以兼容脚本和历史配置

#### 2026-03-01 — 需求拆解 Provider 可见性增强与规则树交互简化

**范围：**
- 后端 / 前端 / 测试 / 文档

**改动摘要：**
- 需求拆解分析结果新增并持久化 `llm_provider` 字段，用于标识本次实际命中的 LLM provider（`openai` / `zhipu`）
- 架构分析页“分析引擎”区域新增 provider 提示标签，LLM 场景可直接看到 `LLM: OpenAI` 或 `LLM: Zhipu`
- 规则树页移除“焦点视图 / 子节点层级 / 水平流程图”切换，统一为垂直全图模式，减少误触导致的视图突变
- 节点点击仅用于选中与编辑，不再自动切换视图模式
- 规则树自动布局间距上调：`nodesep=188`、`ranksep=252`、`marginx=96`、`marginy=84`

**涉及文件：**
- `backend/app/api/architecture.py`
- `backend/app/schemas/architecture.py`
- `backend/app/services/architecture_analyzer.py`
- `backend/app/services/fallback_llm_client.py`
- `backend/app/services/llm_client.py`
- `backend/tests/test_architecture_analyzer.py`
- `backend/tests/test_fallback_llm.py`
- `frontend/src/pages/ArchitectureAnalysis/index.tsx`
- `frontend/src/pages/RuleTree/index.tsx`
- `frontend/src/types/index.ts`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: `POST /api/ai/architecture/analyze` 响应新增 `llm_provider?: string | null`
- Model: 无数据库结构变更（字段写入 `analysis_result` JSON）

**验证记录：**
- `cd backend && pytest -q tests/test_fallback_llm.py tests/test_architecture_analyzer.py`：通过（14 passed）
- `cd frontend && npm run build`：通过（存在既有第三方 `use client` 与 chunk size 警告，不影响功能）

#### 2026-03-01 — 规则树生成稳定性优化（Seed/低温/去重后处理）

**范围：**
- 后端 / 测试 / 文档

**改动摘要：**
- LLM 参数调优：默认 `LLM_TEMPERATURE` 调整为 `0.15`，新增 `LLM_SEED=42`
- `BaseLLMClient` 新增 `seed` 能力：按配置将 `seed` 注入请求 payload，未配置则不传
- OpenAI/智谱 provider 接入统一 `LLM_SEED` 读取；OpenAI SDK 调用链显式透传 `seed`
- 需求拆解阶段1输出截断阈值由 `2000` 提升到 `4000`，降低长流程信息丢失概率
- `LLMAnalyzerProvider` 新增后处理：
  - 同级节点精确去重（`parent_id + type + 归一化 content`）
  - 去重后子节点父链重挂载，保持树结构可导入
  - 节点数告警日志（`<15` / `>40`），仅观测不拦截
- 新增/更新单测覆盖上述行为：`test_base_llm_client.py`、`test_openai_client.py`、`test_architecture_analyzer.py`

**涉及文件：**
- `backend/.env`
- `backend/.env.example`
- `backend/app/services/base_llm_client.py`
- `backend/app/services/openai_client.py`
- `backend/app/services/zhipu_client.py`
- `backend/app/services/architecture_analyzer.py`
- `backend/tests/test_base_llm_client.py`
- `backend/tests/test_openai_client.py`
- `backend/tests/test_architecture_analyzer.py`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无新增接口；`/api/ai/architecture/*` 出参与字段结构不变
- Model: 无数据库结构变更

**验证记录：**
- `pytest -q backend/tests/test_base_llm_client.py backend/tests/test_openai_client.py backend/tests/test_architecture_analyzer.py`：通过（20 passed）
- `pytest -q backend/tests/test_llm_client.py backend/tests/test_fallback_llm.py backend/tests/test_architecture_analyzer.py backend/tests/test_openai_client.py`：通过（26 passed）

#### 2026-03-04 — 规则树可视化迁移到 simple-mind-map（含判断树渲染复用）

**范围：**
- 前端 / 文档

**改动摘要：**
- 规则树页从 ReactFlow 迁移到 `simple-mind-map`，新增 `MindMapWrapper`、`dataAdapter`、`mindMapTheme` 作为统一可视化层
- 新增「画布编辑 -> 后端同步」链路：监听 `data_change`，对比前后树数据后按新增/更新/删除顺序调用规则节点 CRUD
- 规则树工具栏新增导出能力（PNG/SVG/XMind）与文本宽度调节；左侧目录树与画布高亮/聚焦联动保留
- 需求拆解页复用同一 `MindMapWrapper` 以只读方式展示判断树，减少两套可视化实现分叉
- 文档同步更新技术栈、页面交互与设计决策中的树可视化实现描述

**涉及文件：**
- `frontend/src/pages/RuleTree/MindMapWrapper.tsx`
- `frontend/src/pages/RuleTree/dataAdapter.ts`
- `frontend/src/pages/RuleTree/mindMapTheme.ts`
- `frontend/src/pages/RuleTree/index.tsx`
- `frontend/src/pages/ArchitectureAnalysis/index.tsx`
- `frontend/src/types/simple-mind-map-full.d.ts`
- `frontend/package.json`
- `KNOWLEDGE_BASE.md`

**接口/模型变更：**
- API: 无（沿用既有 `rules` / `ai_parse` / `architecture` 接口）
- Model: 无（数据库结构无变更）

**验证记录：**
- `命令`: `rg -n "ReactFlow 可视化规则树|ReactFlow 渲染决策树|树可视化 \\| ReactFlow" KNOWLEDGE_BASE.md | rg -v "命令" || true`
- `结果`: 通过（无命中，现状描述已统一为 simple-mind-map）

---

## 13. 常见问题 (FAQ)

**Q: 本地开发需要安装 PostgreSQL 吗？**
A: 不需要。默认使用 SQLite，零配置即可运行。仅 Docker Compose 部署时使用 PostgreSQL。

**Q: 规则路径是手动创建的吗？**
A: 不是。路径由系统自动推导 (DFS 算法)，每次规则节点变更后自动重新计算。

**Q: 规则节点删除后测试用例会自动失效吗？**
A: 节点采用软删除 (status 设为 deleted)，删除操作会触发影响分析，将关联的测试用例状态标记为 `needs_review`，由 QA 人工复查决定是否废弃。

**Q: 删除节点后，规则树或覆盖矩阵里还会看到这个节点吗？**
A: 不会。后端在规则树接口和覆盖接口都过滤了 `status=deleted` 节点。若页面仍显示旧数据，刷新页面后会同步最新结果。

**Q: AI 解析目前能处理多复杂的需求文本？**
A: 当前版本默认走 `LLM` 解析并返回草稿节点，复杂需求质量显著优于纯分句；若 LLM 调用失败会自动降级为规则分句解析，保证可用性。

**Q: 如何查看 API 文档？**
A: 启动后端后访问 `http://localhost:8000/docs` (Swagger UI) 或 `http://localhost:8000/redoc` (ReDoc)。

**Q: 需求拆解的 AI 分析当前能力如何？**
A: 当前版本已支持两种引擎：
- `mock`：规则/模板分析，稳定可离线运行
- `llm`：基于 SSE（`httpx + text/event-stream`）的两阶段分析（流程图多模态理解 + JSON 结构化生成）
当 `llm` 调用失败、超时或返回结构不合法时，会自动回退到 `MockAnalyzerProvider`，保证接口可用性。

**Q: 页面显示 `Mock（LLM降级）`，一般怎么排查？**
A: 先看几类高频根因：
- 网络连通性问题（常见于受限沙箱或未配置代理）：`api.openai.com` 或 `open.bigmodel.cn` 无法解析/访问，会触发 `ConnectError` 并降级
- LLM 返回结构漂移（字段缺失/类型不符）：例如 `decision_tree` 缺失、`nodes` 不是数组、输出被 `data/result` 包裹或使用 `decisionTree/nodeId/nodeType/parentId` 等别名字段；当前版本会先尝试归一化修正，修正后仍失败才降级
- SSE 兼容性问题：`httpx==0.24.1` 下若代码使用 `iter_lines(decode_unicode=True)` 会抛 `TypeError` 并降级；当前版本已修复为兼容写法
- 进程未重启仍运行旧代码：日志若仍出现旧格式 `LLM payload invalid, fallback to mock (..., error=...)`，说明新版本未生效（新版本日志包含 `payload_summary` / `raw_error` / `normalize_error`）
建议最小自检命令：
- `python -c "import socket; print(socket.gethostbyname('api.openai.com'))"`
- `python -c "import socket; print(socket.gethostbyname('open.bigmodel.cn'))"`
- `curl -I https://api.openai.com`
- `curl -I https://open.bigmodel.cn`
- `cd backend && set -a && source .env && set +a && .venv/bin/python - <<'PY' ... LLMClient.chat_with_json(...) ... PY`

**Q: 需求拆解页显示 `LLM: OpenAI` 或 `LLM: Zhipu` 代表什么？**
A: 这是本次请求实际命中的 provider（来自响应字段 `llm_provider`）。若出现 OpenAI 失败后自动回退智谱，最终会显示 `LLM: Zhipu`。常见 OpenAI 失败原因之一是网关返回 `402 Insufficient Balance`（余额不足）。

**Q: 需求拆解的流程图上传是必须的吗？**
A: 不是。`description_text` 与 `image` 二选一即可发起分析；两者同时提供时会联合分析。当前 Mock 实现会把流程图文件名作为“流程图参考信息”拼接到分析输入，并将图片保存到 `backend/uploads/architecture/`。

**Q: 为什么我已经上传了流程图，还提示“请上传流程图或填写需求描述”？**
A: 根因是前端上传组件在不同路径下返回的文件对象结构不一致，早期逻辑仅读取 `originFileObj`，导致“文件列表已显示但校验判空”。已修复为同时兼容 `UploadFile.originFileObj` 与原始 `File` 两种结构。

**Q: 为什么我已经上传了 XMind，点击“开始解析”仍提示“请先上传 Excel 或 XMind 文件”？**
A: 根因同样是上传组件文件对象结构兼容性问题。旧逻辑在部分路径下只拿到展示对象，解析时读取不到 `originFileObj`。当前版本已修复为上传时保留 `originFileObj`，并在解析时兼容 `UploadFile.originFileObj` 与原始 `File`，避免“已显示文件但判空”的误报。

**Q: 需求拆解导入后会影响已有数据吗？**
A: 导入时会创建新的规则节点，不会修改已有数据。若无关联需求，会自动创建一条新需求 (source_type=flowchart)。导入后自动重算规则路径。

**Q: 删除项目会发生什么？**
A: 项目使用真删除 (非软删除)。由于 SQLAlchemy relationship 配置了 `cascade="all, delete-orphan"`，删除项目会级联删除其下的所有需求、规则节点、测试用例和架构分析记录。

**Q: 为什么删除用例会提示“删除失败”？**
A: 旧版本中，若该用例已被回归推荐结果 `reco_result` 引用，删除时可能触发数据库约束错误。当前版本已修复为级联清理关联 `reco_result` 明细后再删除用例。若仍出现该提示，请确认后端已重启并加载最新代码。

**Q: 用例列表如何按需求筛选？**
A: 前端用例管理页自动传递当前选中的 `selectedRequirementId`，后端通过 `?requirement_id=N` 查询参数，基于用例绑定的规则节点或路径所属需求进行 outerjoin 筛选。

**Q: 用例绑定规则路径时为什么有些路径选不到？**
A: 前端做了路径校验——只有包含已选全部规则节点的路径才会出现在下拉框中。如果切换了已选节点，不匹配的路径会自动被移除并提示。

**Q: 覆盖矩阵为什么要显示需求 ID（例如 `测试拆解 - 需求拆解 (#3)`）？**
A: 因为同一项目下可能存在同名需求。覆盖页按需求 ID 精确统计节点，显示 `#ID` 可以避免误选同名项导致看到错误的节点总数。

**Q: 回归推荐的 FULL 和 CHANGE 有什么区别？**
A: `FULL` 以当前需求全部活跃节点为目标域；`CHANGE` 仅覆盖变更影响域（变更节点 + 祖先 + 子树），并对影响域节点做风险加权增强，适合快速变更回归。

**Q: 推荐结果为什么会包含“推荐原因”和“关键贡献节点”？**
A: 推荐算法在每轮选择后会记录 `gain_node_ids`、`top_contributors` 和 `why_selected`，用于解释该用例在当前轮次带来的新增风险收益，便于 QA 审核推荐结果。

**Q: 推荐页点击“查看用例”后发生了什么？**
A: 前端会跳转到 `/test-cases?focusCaseId={case_id}`；用例页读取参数后自动滚动到目标行并高亮，帮助快速定位推荐用例。

**Q: 需求版本化后，旧版本的规则树还能编辑吗？**
A: 不能。选择旧版本后页面自动进入只读模式，所有编辑操作（新增/修改/删除节点、AI 解析、会话生成等）均被禁用。如需修改，请基于当前最新版本操作，或创建新版本后编辑。

**Q: 版本对比（Diff）显示"算法对比"而不是"语义对比"，是正常的吗？**
A: 是正常的。系统优先使用 LLM 进行语义级对比（生成变更摘要和流程级变更），但当 LLM 调用失败或超时时，会自动回退到基于 SequenceMatcher 的算法对比。算法对比结果是节点级的增删改列表，准确但缺少语义摘要。

**Q: 规则树会话式 AI 生成和原来的"AI 半自动解析"有什么区别？**
A: 两者定位不同：
- **AI 半自动解析**：一次性将需求文本解析为规则节点草稿，适合快速生成初始树
- **会话式 AI 生成**：支持多轮对话，AI 生成后自动审查质量，用户可反复提供修改意见进行增量更新，最终确认导入。适合对生成质量有更高要求、需要迭代优化的场景

**Q: 会话式生成的规则树"确认导入"后，原有规则树会被覆盖吗？**
A: 是的。确认导入时会清除当前需求下的所有旧规则节点，然后写入新生成的节点并重新计算规则路径。建议在确认前先创建新版本，避免丢失原有数据。

**Q: 风险识别的"转节点"操作具体做了什么？**
A: "转节点"会将该风险项转化为一个新的规则树节点（通常作为 condition 类型挂在规则树合适位置），创建后自动重新计算规则路径。这样原本被识别为风险点的内容就纳入了正式的规则覆盖范围。

**Q: 风险项可以删除吗？**
A: 可以。每条风险项右侧有「删除」按钮，点击后会弹出二次确认（Popconfirm），确认后物理删除该风险记录。删除操作不可恢复。

**Q: 测试方案生成和手动创建用例有什么区别？**
A: 测试方案生成是 AI 辅助的两阶段流程：先基于规则树生成测试方案（Markdown 文档 + 结构化测试点列表），再基于方案生成具体测试用例。生成后可人工审查编辑，确认后一键导入用例库。手动创建则是直接在用例管理页逐条填写。

**Q: 测试方案生成的用例会自动绑定规则节点吗？**
A: 会。AI 生成的用例包含 `related_node_ids` 字段，确认导入时会自动将这些节点绑定到用例的 `bound_rule_nodes` 关系。此外系统会检查所有可测试节点（action/branch/exception）的覆盖情况，未覆盖的会自动补充兜底用例。

**Q: 数据库升级需要手动操作吗？**
A: 不需要。应用启动时会自动执行 `ensure_requirements_versioning_columns` 和 `ensure_test_cases_precondition_column`，检测并补充缺失的列和索引。已有数据的 `version` 默认为 1，`requirement_group_id` 默认为空，`precondition` 默认为空字符串。
