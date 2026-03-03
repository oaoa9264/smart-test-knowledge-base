---
name: 规则树思维导图可视化升级
overview: 将规则树的 ReactFlow 可视化从"手动网格坐标布局"升级为"XMind 风格思维导图"，通过 dagre 自动布局 + 自定义节点组件 + 风险着色 + 画布折叠/展开，解决当前"布局混乱、逻辑流向不清晰、不像思维导图"三个核心体验问题。不改后端数据模型。
todos:
  - id: install-dagre
    content: 安装 dagre 和 @types/dagre 依赖
    status: pending
  - id: mindmap-node
    content: 创建 MindMapNode 自定义节点组件，按 node_type 和 risk_level 区分外观
    status: pending
  - id: mindmap-css
    content: 创建 mindmap.css 样式文件，定义各类型节点的形状、颜色、风险色带
    status: pending
  - id: dagre-layout
    content: 重写 toFlowNodes，用 dagre 自动布局替换手动坐标计算，支持 LR/TB 方向切换
    status: pending
  - id: edge-style
    content: 升级边样式：smoothstep/bezier + 箭头标记 + 动画方向
    status: pending
  - id: collapse-expand
    content: 实现画布内子树折叠/展开功能（节点右侧 +/- 按钮 + 子节点计数徽章）
    status: pending
  - id: verify-build
    content: 验证 npm run build 通过，检查 lint 错误，测试不同规模的规则树展示效果
    status: pending
isProject: false
---

# 规则树思维导图可视化升级

## 问题诊断

当前 `[frontend/src/pages/RuleTree/index.tsx](frontend/src/pages/RuleTree/index.tsx)` 的 `toFlowNodes` 函数使用 `x = 220 * depth, y = 110 * siblingOrder` 的固定网格布局，导致：

- 不同父节点的子节点纵向重叠
- 节点多时层级关系不可辨认
- 所有节点外观完全一致，无法区分类型

## 改造方案

### 1. 引入 dagre 自动布局

- 安装 `dagre` (`@types/dagre`) 库，用于自动计算树的层级布局
- 布局方向设为 `LR`（左到右），模拟 XMind 水平思维导图
- 替换 `toFlowNodes` 中的手动坐标计算，改为 dagre 自动排列

```typescript
import dagre from "dagre";

function getLayoutedElements(nodes, edges, direction = "LR") {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 180 });
  nodes.forEach((node) => g.setNode(node.id, { width: 200, height: 60 }));
  edges.forEach((edge) => g.setEdge(edge.source, edge.target));
  dagre.layout(g);
  return nodes.map((node) => {
    const pos = g.node(node.id);
    return { ...node, position: { x: pos.x - 100, y: pos.y - 30 } };
  });
}
```

### 2. 自定义节点组件 — 按类型区分外观

创建 `frontend/src/pages/RuleTree/MindMapNode.tsx`：

- **root**: 圆角胶囊形，深蓝背景白字，较大字体
- **condition**: 菱形感（对角裁切或内缩边框），橙色系边框
- **branch**: 标准圆角矩形，蓝色系
- **action**: 圆角矩形，绿色系边框
- **exception**: 圆角矩形，红色系边框，虚线

每个节点显示：

- 节点内容（截断 + tooltip）
- 左上角小标签显示类型（如 `条件`、`动作`）
- 右上角风险等级色块（critical=红, high=橙, medium=黄, low=绿）

### 3. 风险等级着色

在节点的左侧或上方加一条**风险色带**：

- `critical` → `#ff4d4f`
- `high` → `#fa8c16`
- `medium` → `#fadb14`
- `low` → `#52c41a`

### 4. 边样式升级

- 使用 `smoothstep` 或 `bezier` 边类型替代默认直线
- 边末端加箭头标记（`markerEnd`）
- 从父到子的方向清晰可见

### 5. 画布内折叠/展开

- 在每个有子节点的节点右侧显示一个 `+/-` 按钮
- 点击后折叠/展开该子树，折叠时显示子节点计数徽章（如 `+5`）
- 利用 ReactFlow 的节点隐藏能力实现（不需要重新请求数据）

### 6. 布局方向切换

- 在工具栏提供"水平 / 垂直"布局切换按钮
- 水平 (`LR`)：XMind 思维导图风格（默认）
- 垂直 (`TB`)：传统流程图风格

## 涉及文件

- **修改**: `[frontend/src/pages/RuleTree/index.tsx](frontend/src/pages/RuleTree/index.tsx)` — 替换布局算法，注册自定义节点，升级边样式
- **新增**: `frontend/src/pages/RuleTree/MindMapNode.tsx` — 自定义节点组件
- **新增**: `frontend/src/pages/RuleTree/mindmap.css` — 节点样式
- **修改**: `[frontend/package.json](frontend/package.json)` — 添加 `dagre` + `@types/dagre` 依赖

## 不改什么

- **不改后端**: 数据模型、API 接口、规则引擎、覆盖率、影响分析、推荐算法全部保持不变
- **不改数据结构**: RuleNode 的 parent_id 树结构保持不变
- **不改左侧目录树**: Ant Design Tree 组件保留，仅升级右侧 ReactFlow 画布
