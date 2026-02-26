# 自动化测试知识库 MVP — 项目知识库

> 本文档是项目的完整知识库，覆盖项目概述、技术架构、数据模型、API 接口、前端页面、核心业务逻辑、开发规范等，供团队成员快速上手与日常参考。

---

## 1. 项目概述

### 1.1 项目名称

**自动化测试知识库 MVP (Test Knowledge Base MVP)**

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
| **P1+** | AI 辅助架构拆解 | 上传流程图 + 文字描述，AI 生成判断树/测试方案/风险点/用例矩阵，支持一键导入正式库 |

### 1.4 核心业务流

```
创建项目 → 创建需求 → 构建规则树 → 创建测试用例(绑定规则节点)
                          ↓                        ↓
                    AI 解析辅助              覆盖矩阵自动计算
                          ↓                        ↓
                    规则变更 → 影响分析 → 标记 needs_review

                    ┌────────────────────────────────────────┐
                    │      AI 辅助架构拆解 (P1+ 新增)          │
                    │                                        │
                    │ 上传流程图/描述 → AI 分析 → 生成四产物    │
                    │   ├─ 判断树 (决策节点树)                 │
                    │   ├─ 测试方案 (Markdown)                │
                    │   ├─ 风险点列表 (含缓解建议)             │
                    │   └─ 用例矩阵 (路径级测试用例)           │
                    │ → 人工确认 → 一键导入正式库               │
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
| Pytest | 7.4.4 | 单元测试 & 接口测试 |
| httpx | 0.24.1 | 测试 HTTP 客户端 |

#### 前端 (Frontend)

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.3.1 | UI 框架 |
| TypeScript | 5.8.2 | 类型安全 |
| Vite | 2.9.18 | 构建工具 & 开发服务器 |
| Ant Design | 5.27.0 | UI 组件库 |
| @ant-design/icons | 5.6.1 | Ant Design 图标库 |
| ReactFlow | 11.11.4 | 规则树/判断树可视化 (节点拖拽、连线、MiniMap、画布平移/缩放) |
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
│   │   │   ├── architecture.py     # AI 辅助架构拆解接口 (P1+ 新增)
│   │   │   ├── coverage.py         # 覆盖矩阵接口
│   │   │   ├── projects.py         # 项目 & 需求接口
│   │   │   ├── rules.py            # 规则树 CRUD & 影响分析接口
│   │   │   └── testcases.py        # 测试用例接口
│   │   ├── core/
│   │   │   └── database.py         # 数据库连接 & Session 管理
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── entities.py         # SQLAlchemy 实体模型
│   │   ├── schemas/
│   │   │   ├── __init__.py         # Schema 统一导出
│   │   │   ├── architecture.py     # 架构拆解 Pydantic DTO (P1+ 新增)
│   │   │   ├── project.py          # 项目/需求 Pydantic DTO (含 Create/Update/Read)
│   │   │   ├── rule.py             # 规则节点/路径 Pydantic DTO
│   │   │   └── testcase.py         # 测试用例 Pydantic DTO (含 Create/Update/Read/UpdateStatus)
│   │   ├── services/
│   │   │   ├── ai_parser.py        # AI 需求解析逻辑
│   │   │   ├── architecture_analyzer.py  # 架构拆解分析引擎 (P1+ 新增)
│   │   │   ├── coverage.py         # 覆盖率矩阵计算
│   │   │   ├── impact.py           # 变更影响分析
│   │   │   └── rule_engine.py      # 规则路径推导 (DFS)
│   │   └── main.py                 # FastAPI 应用入口
│   ├── tests/
│   │   ├── conftest.py             # 测试配置
│   │   ├── test_api_smoke.py       # API 冒烟测试
│   │   ├── test_architecture_analyzer.py  # 架构拆解分析单测 (P1+ 新增)
│   │   ├── test_coverage_and_impact.py    # 覆盖率 & 影响分析单测
│   │   ├── test_projects_crud_api.py      # 项目 & 需求 CRUD API 测试
│   │   ├── test_rule_engine.py     # 规则引擎单测
│   │   └── test_testcases_api.py   # 测试用例 CRUD & 需求筛选 API 测试
│   ├── uploads/                    # 上传文件目录 (运行时生成)
│   │   └── architecture/           # 架构流程图存储
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/                    # API 调用封装
│   │   │   ├── architecture.ts     # 架构拆解 API (P1+ 新增)
│   │   │   ├── client.ts           # Axios 实例 (baseURL 配置)
│   │   │   ├── coverage.ts         # 覆盖矩阵 API
│   │   │   ├── projects.ts         # 项目 & 需求 API
│   │   │   ├── rules.ts            # 规则树 & AI 解析 API
│   │   │   └── testcases.ts        # 测试用例 API
│   │   ├── pages/
│   │   │   ├── ArchitectureAnalysis/  # AI 架构拆解页 (P1+ 新增)
│   │   │   ├── ProjectList/        # 项目 & 需求管理页
│   │   │   ├── RuleTree/           # 规则树可视化编辑页
│   │   │   ├── TestCases/          # 测试用例管理页
│   │   │   └── Coverage/           # 覆盖矩阵页
│   │   ├── stores/
│   │   │   └── appStore.ts         # 全局状态 (Zustand)
│   │   ├── types/
│   │   │   └── index.ts            # TypeScript 类型定义
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
| steps | Text | NOT NULL | 执行步骤 |
| expected_result | Text | NOT NULL | 预期结果 |
| risk_level | Enum | NOT NULL, 默认 medium | 风险等级 |
| status | Enum | NOT NULL, 默认 active | 用例状态 |
| created_at | DateTime | NOT NULL | 创建时间 |

**用例状态 (TestCaseStatus):**
- `active` — 有效
- `needs_review` — 需要复查 (规则变更触发)
- `invalidated` — 已失效

#### ArchitectureAnalysis (架构拆解分析记录，P1+ 新增)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 分析记录 ID |
| project_id | Integer | FK → projects.id, NOT NULL | 所属项目 |
| requirement_id | Integer | FK → requirements.id, 可选 | 关联需求 (导入时自动创建或绑定) |
| title | String(255) | NOT NULL | 分析标题 |
| image_path | Text | 可选 | 上传的流程图文件路径 |
| description_text | Text | 可选 | 文字描述 |
| analysis_result | Text | 可选 | JSON 序列化的分析结果 (含判断树/测试方案/风险点/用例) |
| status | Enum | NOT NULL, 默认 pending | 分析状态 |
| created_at | DateTime | NOT NULL, 默认 UTC now | 创建时间 |

**分析状态 (AnalysisStatus):**
- `pending` — 待处理
- `completed` — 已完成分析
- `imported` — 已导入正式库

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
- 规则树查询会过滤 `status=deleted` 节点，避免已软删除节点继续出现在前端画布

**实现位置：**
- `backend/app/api/rules.py` → `get_rule_tree` (`RuleNode.status != NodeStatus.deleted`)

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
| POST | `/api/ai/parse` | 解析需求文本为规则草稿 | `{raw_text}` | `{nodes: AIParseNode[]}` |

**当前实现逻辑：** 按中文句号/逗号分割文本，第一个子句作为 condition 节点，后续子句作为 branch 节点，自动构建父子链。若仅一个子句则标记为 root。

### 4.7 AI 辅助架构拆解 (`/api/ai/architecture`，P1+ 新增)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/ai/architecture/analyze` | 架构拆解分析 | `multipart/form-data: {project_id, requirement_id?, title?, description_text, image?}` | ArchitectureAnalyzeResponse (201) |
| GET | `/api/ai/architecture/{analysis_id}` | 获取分析详情 | — | ArchitectureAnalysisRead |
| POST | `/api/ai/architecture/{analysis_id}/import` | 导入分析结果到正式库 | `{import_decision_tree?, import_test_cases?, import_risk_points?}` | ArchitectureImportResult |

**ArchitectureAnalyzeResponse 响应结构：**
```json
{
  "id": 1,
  "decision_tree": {
    "nodes": [
      {"id": "dt_1", "type": "root", "content": "...", "parent_id": null, "risk_level": "medium"},
      {"id": "dt_2", "type": "condition", "content": "...", "parent_id": "dt_1", "risk_level": "high"}
    ]
  },
  "test_plan": {
    "markdown": "# AI 生成测试方案\n## 1. 测试范围\n...",
    "sections": ["scope", "strategy", "environment", "schedule", "exit_criteria"]
  },
  "risk_points": [
    {"id": "rp_1", "description": "...", "severity": "critical", "mitigation": "...", "related_node_ids": ["dt_2"]}
  ],
  "test_cases": [
    {"title": "提现流程架构拆解-路径用例1", "steps": "依次验证: ...", "expected_result": "...", "risk_level": "high", "related_node_ids": ["dt_1", "dt_2"]}
  ]
}
```

**ArchitectureImportResult 响应结构：**
```json
{
  "analysis_id": 1,
  "requirement_id": 5,
  "imported_rule_nodes": 6,
  "imported_test_cases": 3,
  "updated_risk_nodes": 2
}
```

**关键机制：**
- 分析接口 (`/analyze`) 接受 `multipart/form-data`，支持上传流程图图片 (可选)
- 分析引擎通过 Provider 模式选择 (`ANALYZER_PROVIDER` 环境变量)：当前为 `MockAnalyzerProvider` (规则分句)，预留 `LLMAnalyzerProvider` 接口
- 导入接口 (`/import`) 支持选择性导入三种产物：判断树节点、风险标注、测试用例
- 导入时若无关联需求会自动创建新需求，并自动重算规则路径
- 上传的图片存储在 `backend/uploads/architecture/` 目录，通过 `/uploads/architecture/` 静态路径访问

---

## 5. 核心业务逻辑

### 5.1 规则路径推导 (`rule_engine.py`)

**算法:** DFS (深度优先搜索) 从根节点到叶子节点遍历所有路径。

**输入:** 节点列表 `[{id, parent_id}]`

**输出:** 所有根到叶的路径 `[[node_id, ...], ...]`

**流程：**
1. 按 `parent_id` 构建父子映射
2. 找到所有根节点 (`parent_id == None`)
3. 从每个根节点 DFS 递归，遇到叶子节点时记录完整路径
4. 返回所有路径

**触发时机：** 每次规则节点创建/更新/删除后自动调用

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

**当前版本为规则拆分的简单实现：**
1. 将中文句号替换为逗号
2. 按逗号分割文本为子句
3. 依次生成临时节点（首个为 condition，其余为 branch）
4. 构建线性父子关系链
5. 返回草稿节点供用户确认后导入

> 后续可接入 LLM API 实现更智能的需求理解与规则拆解。

### 5.5 AI 辅助架构拆解 (`architecture_analyzer.py`，P1+ 新增)

**架构模式：** Provider 模式，通过 `ANALYZER_PROVIDER` 环境变量选择分析引擎。

**Provider 层级：**
- `ArchitectureAnalyzerProvider` — 抽象基类
- `MockAnalyzerProvider` — 规则/模板分析引擎 (当前默认)
- `LLMAnalyzerProvider` — LLM 集成占位 (当前回退到 Mock)

**MockAnalyzerProvider 分析流程：**

1. **文本分句** (`_split_sentences`) — 按句号/叹号/问号/分号/换行拆分
2. **构建判断树** (`_build_decision_tree`) — 四产物之一
   - 第一句作为 root 节点
   - 后续每句尝试拆分「条件-动作」对 (按「则」「那么」「->」「，」分割)
   - 条件部分判断是否含 condition 关键词 (如果/当/若/是否/检查/校验)
   - 动作部分判断是否为异常文本 (异常/失败/超时/错误/拒绝)
   - 所有条件/分支节点直接挂在 root 下，动作节点挂在对应条件下
3. **生成测试方案** (`_build_test_plan`) — 四产物之二
   - 生成包含 5 个章节的 Markdown 文档：测试范围、测试策略、环境要求、进度安排、退出标准
4. **提取风险点** (`_build_risk_points`) — 四产物之三
   - 筛选 critical/high 风险节点，生成风险描述与缓解建议
5. **生成测试用例** (`_build_generated_cases`) — 四产物之四
   - 对判断树执行 DFS 路径推导，为每条路径生成一个测试用例
   - 用例风险等级取路径中最高风险等级
   - 用例标题命名规则：优先使用「分析标题-路径用例N」，无分析标题时回退为「架构路径用例 N」

**风险等级自动推断 (`_content_to_risk`)：**
- critical: 包含「资金/转账/并发/安全/权限/超时」
- high: 包含「失败/异常/错误/拒绝/重试」
- medium: 包含「检查/校验/不足」
- low: 其他

**导入流程 (`architecture.py` API 层)：**
1. 判断树导入 — 按拓扑顺序 (父先子后) 将节点写入 RuleNode 表，维护 ID 映射
2. 风险标注导入 — 根据分析结果中的 risk_points 更新对应 RuleNode 的 risk_level
3. 用例导入 — 将 test_cases 写入 TestCase 表，绑定关联的 RuleNode
4. 导入完成后自动重算规则路径 (`_regenerate_paths`)
5. 若无关联需求，自动创建新 Requirement (source_type=flowchart)

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
│ ○ 架构拆解               │                               │
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
| **规则树** | `/rule-tree` | ReactFlow 可视化规则树、节点 CRUD、AI 解析导入、变更影响提示 |
| **用例管理** | `/test-cases` | 用例 CRUD (新建/查看/编辑/删除)、绑定规则节点/路径、按需求筛选、路径校验、状态标签 |
| **覆盖矩阵** | `/coverage` | 按当前选中需求展示覆盖率仪表盘、高风险告警、节点覆盖详情表 |
| **架构拆解** | `/architecture` | 上传流程图、填写描述、AI 分析、判断树/测试方案/风险点/用例矩阵四 Tab 预览、选择性导入 |

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
2. 需求表格展示 ID / 标题 / 来源类型 (中文标签)，每行含「查看」「修改」「删除」
3. 「修改」→ Modal 表单含来源类型 Select (需求文档/流程图/接口文档)
4. 点击需求行 → 设为当前选中需求

### 6.4 规则树页面交互流程

1. 选择需求 → 加载规则树 (ReactFlow 渲染) 并自动执行 `fitView` 对齐可视区域
2. 画布导航增强：支持空白区域拖拽平移 (`panOnDrag`) + 滚轮自由平移 (`panOnScrollMode=Free`)，可上下左右浏览大图
3. 缩放增强：将最小缩放放宽到 `minZoom=0.05`，节点量很大时仍可缩小查看全量结构
4. 节点/边刷新后会再次自动 `fitView` (`padding=0.2, minZoom=0.05`)，避免新增大量节点后视野丢失
5. 点击节点 → 打开编辑抽屉 (Drawer)，可修改内容/类型/风险等级
6. 保存修改 → 后端返回影响分析结果 → 页面显示 Alert 提示受影响用例
7. 点击「AI 半自动解析」→ 输入需求文本 → 生成草稿表格预览 → 确认导入
8. 新增节点 → Modal 表单，可选择父节点

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
8. 「修改」→ Modal 表单预填当前值，支持修改绑定关系与状态
9. 「删除」→ Popconfirm 确认后调 DELETE API
10. 页面底部有「变更影响分析提示」Alert，说明规则更新后用例会自动标记

**需求筛选：** 页面加载时传入当前选中的 `selectedRequirementId`，通过 `?requirement_id=N` 参数筛选用例

### 6.6 架构拆解页面交互流程 (P1+ 新增)

**页面布局：**
- 上半部分：左侧为流程图拖拽上传区 (Upload.Dragger)，右侧为表单 (标题 + 文字描述 textarea)
- 下半部分：分析完成后显示四 Tab 结果面板

**操作流程：**
1. 选择项目 → 填写分析标题和架构文字描述 → 可选上传流程图
2. 点击「开始分析」→ 调用 `/api/ai/architecture/analyze` → 返回四产物
3. Tab 1「判断树」→ ReactFlow 渲染决策树 (节点按风险等级着色)，并支持拖拽平移 + 滚轮自由平移 + `minZoom=0.05` 全图缩放查看
4. Tab 2「测试方案」→ react-markdown 渲染 AI 生成的 Markdown 测试方案
5. Tab 3「关键风险点」→ 卡片列表，每张卡片含风险等级 Tag + 描述 + 缓解建议
6. Tab 4「用例矩阵」→ 表格展示路径级测试用例 (标题/步骤/预期/风险等级)
   - 用例标题默认以分析标题为前缀（`{分析标题}-路径用例N`）
7. 底部三个 Checkbox 控制导入选项 → 点击「导入到正式库」→ 写入规则树 + 用例 + 风险标注

### 6.7 覆盖矩阵页面展示

- **前置条件** — 必须已选中项目和需求；未选需求时页面提示「请先选择需求，再查看该需求的节点覆盖率」
- **取数口径** — 覆盖页调用 `/api/coverage/projects/{project_id}/requirements/{requirement_id}`，只统计当前需求的规则节点
- **软删除过滤** — 已软删除节点不会出现在覆盖矩阵列表，也不会计入“总节点数”
- **覆盖率圆环图** — 以百分比展示当前需求节点覆盖率（例如需求 A 有 14 个节点则显示 `x/14`，需求 B 有 1 个节点则显示 `x/1`）
- **高风险告警卡片** — 列出当前需求中所有 critical 且未覆盖的节点
- **覆盖详情表** — 每行一个当前需求规则节点，展示风险等级、覆盖用例数、未覆盖路径数，支持按风险权重排序

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

应用启动时通过 `Base.metadata.create_all(bind=engine)` 自动创建所有表，无需手动迁移。同时自动创建 `uploads/` 目录用于文件存储，并通过 `StaticFiles` 挂载 `/uploads` 路径提供静态文件访问。

### 7.3 Session 管理

使用 FastAPI 的 `Depends(get_db)` 注入 SQLAlchemy Session，每次请求获取一个新 Session，请求结束后自动关闭。

---

## 8. 开发指南

### 8.1 本地开发

**启动后端：**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

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
- `test_rule_engine.py` — 规则路径推导的正确性 (DFS 算法)
- `test_coverage_and_impact.py` — 覆盖率计算 & 影响分析标记逻辑
- `test_api_smoke.py` — 全链路 API 冒烟测试 (项目→需求→规则→用例→覆盖矩阵→AI解析)；含回归用例：删除节点后规则树与覆盖矩阵不再返回该节点
- `test_architecture_analyzer.py` — 架构拆解分析引擎单测 + 架构拆解全链路 API 测试 (分析→查看→导入→验证规则树和用例)
- `test_projects_crud_api.py` — 项目 & 需求完整 CRUD API 测试 (创建→查看→更新→删除→404 验证)
- `test_testcases_api.py` — 测试用例 CRUD API 测试 (创建→查看→更新→删除) + 按需求 ID 筛选用例、更新绑定关系验证、`status` 字段创建/更新回归验证

### 8.4 环境变量

**后端 (`backend/.env.example`):**

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| DATABASE_URL | sqlite:///./test_knowledge_base.db | 数据库连接串 |
| ANALYZER_PROVIDER | mock | 架构拆解分析引擎 (`mock` 或 `llm`) |

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
  ├── ai_parser — AI 需求解析
  └── architecture_analyzer — AI 架构拆解 (Provider 模式)

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
  ├── 统一使用 Axios 实例 (baseURL + 15s 超时)
  ├── projects — CRUD (create/list/get/update/delete) 项目 & 需求
  ├── testcases — CRUD (create/list/get/update/delete) 测试用例 + 需求筛选
  ├── rules — 规则树 CRUD + AI 解析 + 影响预览
  ├── coverage — 覆盖矩阵查询
  └── architecture — 架构拆解分析/查看/导入

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
| 树可视化 | ReactFlow | 支持节点拖拽、连线、MiniMap、画布平移 (拖拽/滚轮) 与小比例缩放，适合规则树和判断树场景 |
| 规则路径 | 自动派生 | 节点变更时自动 DFS 重算，避免手动维护路径的不一致 |
| 节点删除 | 软删除 (status=deleted) | 保留历史数据，不破坏路径和绑定关系 |
| 影响分析 | 节点级直接关联 | MVP 阶段按节点绑定关系直接标记，后续可扩展路径级分析 |
| 数据库 | SQLite 本地 / PostgreSQL 生产 | 开发零配置，生产环境仅需切换 DATABASE_URL |
| AI 解析 | 规则分句 | MVP 阶段简单实现，后续可替换为 LLM 接口 |
| 架构拆解引擎 | Provider 模式 | 抽象基类 + 具体实现，便于后续接入 LLM/多模型切换 |
| 文件上传 | 本地磁盘 + 静态挂载 | MVP 阶段简单可靠，后续可迁移到对象存储 |
| Markdown 渲染 | react-markdown | 测试方案以 Markdown 生成，前端直接渲染，灵活度高 |

---

## 11. 未来演进方向

| 方向 | 说明 |
|------|------|
| **P2: LLM 驱动的智能解析** | 接入大模型 API 替换 MockAnalyzerProvider，支持多模态 (图片 + 文本) 架构理解 |
| **P2: 用例自动生成** | 基于规则路径自动生成测试用例建议 |
| **P2: 架构分析历史管理** | 分析记录列表、对比、重新分析 |
| **P2: 版本历史与回滚** | 规则节点的完整变更历史记录和版本回溯 |
| **P2: 批量操作** | 支持批量导入/导出规则和用例 |
| **P2: 权限与协作** | 多用户角色、权限控制、操作审计日志 |
| **P2: 数据库迁移** | 引入 Alembic 进行 schema 版本管理 |
| **P2: 文件存储升级** | 从本地磁盘迁移到对象存储 (S3/OSS) |
| **P3: 执行结果关联** | 对接 CI/CD，自动采集测试执行结果 |
| **P3: 可视化增强** | 覆盖热力图、路径高亮、节点搜索 |

---

## 12. 常见问题 (FAQ)

**Q: 本地开发需要安装 PostgreSQL 吗？**
A: 不需要。默认使用 SQLite，零配置即可运行。仅 Docker Compose 部署时使用 PostgreSQL。

**Q: 规则路径是手动创建的吗？**
A: 不是。路径由系统自动推导 (DFS 算法)，每次规则节点变更后自动重新计算。

**Q: 规则节点删除后测试用例会自动失效吗？**
A: 节点采用软删除 (status 设为 deleted)，删除操作会触发影响分析，将关联的测试用例状态标记为 `needs_review`，由 QA 人工复查决定是否废弃。

**Q: 删除节点后，规则树或覆盖矩阵里还会看到这个节点吗？**
A: 不会。后端在规则树接口和覆盖接口都过滤了 `status=deleted` 节点。若页面仍显示旧数据，刷新页面后会同步最新结果。

**Q: AI 解析目前能处理多复杂的需求文本？**
A: 当前版本为简单的句号/逗号分句实现，适合短句型 PRD。复杂场景建议后续接入 LLM。

**Q: 如何查看 API 文档？**
A: 启动后端后访问 `http://localhost:8000/docs` (Swagger UI) 或 `http://localhost:8000/redoc` (ReDoc)。

**Q: 架构拆解的 AI 分析当前能力如何？**
A: 当前版本使用 `MockAnalyzerProvider`，基于规则/模板的文本分析 (分句 + 关键词匹配推断节点类型和风险等级)。适合结构化的中文业务描述。设置 `ANALYZER_PROVIDER=llm` 可切换到 LLM Provider，但当前仍回退到 Mock 实现，待接入真实 LLM API。

**Q: 架构拆解的流程图上传是必须的吗？**
A: 不是。图片上传为可选项，当前版本仅基于文字描述进行分析。图片会保存到 `backend/uploads/architecture/`，为后续多模态 LLM 分析预留。

**Q: 架构拆解导入后会影响已有数据吗？**
A: 导入时会创建新的规则节点和测试用例，不会修改已有数据。若无关联需求，会自动创建一条新需求 (source_type=flowchart)。导入后自动重算规则路径。

**Q: 删除项目会发生什么？**
A: 项目使用真删除 (非软删除)。由于 SQLAlchemy relationship 配置了 `cascade="all, delete-orphan"`，删除项目会级联删除其下的所有需求、规则节点、测试用例和架构分析记录。

**Q: 用例列表如何按需求筛选？**
A: 前端用例管理页自动传递当前选中的 `selectedRequirementId`，后端通过 `?requirement_id=N` 查询参数，基于用例绑定的规则节点或路径所属需求进行 outerjoin 筛选。

**Q: 用例绑定规则路径时为什么有些路径选不到？**
A: 前端做了路径校验——只有包含已选全部规则节点的路径才会出现在下拉框中。如果切换了已选节点，不匹配的路径会自动被移除并提示。

**Q: 覆盖矩阵为什么要显示需求 ID（例如 `测试拆解 - 架构拆解 (#3)`）？**
A: 因为同一项目下可能存在同名需求。覆盖页按需求 ID 精确统计节点，显示 `#ID` 可以避免误选同名项导致看到错误的节点总数。
