# 自动化测试知识库 MVP (P0 + P1)

基于两份方案文档落地的可运行版本，当前实现范围：

- P0: 规则树可视化 CRUD、用例管理与规则绑定、覆盖矩阵
- P1: AI 半自动解析草稿导入、规则变更影响分析（自动标记 `needs_review`）
- P1+: AI 辅助架构拆解（上传流程图+描述，生成判断树/测试方案/风险点/用例矩阵并可一键导入）

## 目录结构

```text
.
├── backend
├── frontend
├── docker-compose.yml
└── docs/plans
```

## 本地启动

### 1) 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2) 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认地址: `http://localhost:5173`
后端地址: `http://localhost:8000`

## 一键启动 (Docker Compose)

```bash
docker compose up --build
```

## 关键 API

- `POST /api/projects` 创建项目
- `POST /api/projects/{project_id}/requirements` 创建需求
- `POST /api/rules/nodes` 创建规则节点
- `PUT /api/rules/nodes/{node_id}` 更新节点并触发影响分析
- `GET /api/rules/requirements/{requirement_id}/tree` 获取规则树
- `POST /api/testcases` 创建测试用例并绑定节点/路径
- `GET /api/coverage/projects/{project_id}` 获取覆盖矩阵
- `POST /api/ai/parse` AI 半自动解析需求文本草稿
- `POST /api/ai/architecture/analyze` 架构拆解分析（multipart）
- `GET /api/ai/architecture/{analysis_id}` 获取拆解分析详情
- `POST /api/ai/architecture/{analysis_id}/import` 导入判断树/风险/用例到正式库

## 测试

当前包含后端核心单元/接口烟测：

```bash
pytest backend/tests -q
```
