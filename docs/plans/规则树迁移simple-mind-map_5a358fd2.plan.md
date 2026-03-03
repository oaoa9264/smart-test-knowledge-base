---
name: 规则树迁移simple-mind-map
overview: 将规则树可视化从 ReactFlow + Dagre 完整迁移到 simple-mind-map，获得 XMind 级别的思维导图体验，同时保留所有现有的节点 CRUD、AI 解析、搜索导航等业务功能。
todos:
  - id: install-deps
    content: 安装 simple-mind-map 依赖，移除 reactflow/dagre（确认无其他页面使用）
    status: pending
  - id: data-adapter
    content: 实现 dataAdapter.ts：RuleNode[] 扁平数据 <-> simple-mind-map 嵌套树数据的双向转换
    status: pending
  - id: mind-map-wrapper
    content: 实现 MindMapWrapper.tsx：React 封装组件，包含初始化、事件绑定、数据同步、销毁生命周期
    status: pending
  - id: custom-theme
    content: 实现 mindMapTheme.ts：自定义主题，映射 5 种节点类型和 4 种风险等级到不同视觉样式
    status: pending
  - id: rewrite-page
    content: 重写 RuleTree/index.tsx：用 MindMapWrapper 替换 ReactFlow，保留左侧目录、Drawer 编辑、Modal 新增、AI 解析等所有业务功能
    status: pending
  - id: data-sync
    content: 实现画布编辑 -> 后端同步机制：监听 data_change 事件，diff 新旧数据，调用 CRUD API 持久化
    status: pending
  - id: toolbar
    content: 添加工具栏：导出（PNG/SVG/XMind）、主题切换、布局切换按钮
    status: pending
  - id: cleanup
    content: 删除废弃文件（MindMapNode.tsx、mindmap.css、vendor/dagre.ts），清理 package.json
    status: pending
isProject: false
---

# 规则树迁移到 simple-mind-map 方案

## 背景

当前规则树使用 ReactFlow v11 + 自定义 Dagre 布局，功能完备但视觉体验不够思维导图化。迁移到 [simple-mind-map](https://github.com/wanglin2/mind-map) 可以获得：

- XMind 风格的视觉体验（圆角、贝塞尔曲线连线、多种布局）
- 内置主题切换
- 导出 PNG/SVG/PDF/XMind 格式
- 键盘快捷键（Tab 插入子节点、Enter 插入兄弟节点、Delete 删除等）
- 拖拽调整节点位置和层级
- 更优雅的折叠/展开动画

## 核心改动范围

### 涉及文件

| 操作   | 文件                                                                                                                         |
| ------ | ---------------------------------------------------------------------------------------------------------------------------- |
| 重写   | [frontend/src/pages/RuleTree/index.tsx](frontend/src/pages/RuleTree/index.tsx)（主页面，约 800 行）                          |
| 新建   | `frontend/src/pages/RuleTree/MindMapWrapper.tsx`（simple-mind-map 的 React 封装）                                            |
| 新建   | `frontend/src/pages/RuleTree/mindMapTheme.ts`（自定义主题，映射节点类型和风险色）                                            |
| 新建   | `frontend/src/pages/RuleTree/dataAdapter.ts`（RuleNode[] 扁平数据 <-> 嵌套树数据转换）                                       |
| 删除   | [frontend/src/pages/RuleTree/MindMapNode.tsx](frontend/src/pages/RuleTree/MindMapNode.tsx)（ReactFlow 自定义节点，不再需要） |
| 删除   | [frontend/src/pages/RuleTree/mindmap.css](frontend/src/pages/RuleTree/mindmap.css)（旧样式，不再需要）                       |
| 可删除 | [frontend/src/vendor/dagre.ts](frontend/src/vendor/dagre.ts)（自定义 Dagre 实现，不再需要）                                  |
| 修改   | [frontend/package.json](frontend/package.json)（添加 simple-mind-map，可移除 reactflow/dagre）                               |

### 不涉及的文件（无需改动）

- 后端 API、Schema、模型层 -- 数据结构不变
- `frontend/src/api/rules.ts` -- API 调用层不变
- `frontend/src/types/index.ts` -- RuleNode/RuleTree 类型不变

## 数据格式适配

当前 `RuleNode[]` 是扁平数组 + `parent_id` 引用关系，simple-mind-map 需要嵌套树结构。需要一个 adapter 层做双向转换：

```typescript
// 当前格式 (后端返回)
interface RuleNode {
  id: string;
  parent_id: string | null;
  node_type: "root" | "condition" | "branch" | "action" | "exception";
  content: string;
  risk_level: "critical" | "high" | "medium" | "low";
}

// simple-mind-map 格式
interface MindMapData {
  data: {
    text: string;
    uid: string; // 映射 RuleNode.id
    nodeType: string; // 映射 node_type
    riskLevel: string; // 映射 risk_level
    // 自定义样式字段
    borderColor?: string;
    backgroundColor?: string;
    shape?: string; // 如 condition 用菱形
  };
  children: MindMapData[];
}
```

**转换函数**：`ruleNodesToMindMapData(nodes: RuleNode[]) -> MindMapData` 和 `mindMapDataToRuleNodes(data: MindMapData) -> RuleNode[]`

## React 封装组件 (MindMapWrapper)

simple-mind-map 是原生 JS 库，需用 `useRef` + `useEffect` 封装成 React 组件：

```typescript
// 核心思路
function MindMapWrapper({ data, onNodeClick, onDataChange, ... }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mindMapRef = useRef<MindMap | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const mindMap = new MindMap({
      el: containerRef.current,
      data: data,
      layout: 'logicalStructure',  // 逻辑结构图，最接近规则树
      theme: 'ruleTreeTheme',      // 自定义主题
      // ... 更多配置
    });

    // 注册插件
    MindMap.usePlugin(MiniMap);
    MindMap.usePlugin(Export);
    MindMap.usePlugin(Drag);
    MindMap.usePlugin(KeyboardNavigation);

    // 绑定事件
    mindMap.on('node_click', (node) => onNodeClick?.(node));
    mindMap.on('data_change', (data) => onDataChange?.(data));

    mindMapRef.current = mindMap;
    return () => mindMap.destroy();
  }, []);

  // 数据更新时同步
  useEffect(() => {
    mindMapRef.current?.setData(data);
  }, [data]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
}
```

## 自定义主题与节点样式

通过 simple-mind-map 的主题 API 注册自定义 `ruleTreeTheme`，将节点类型和风险等级映射到不同视觉样式：

- **root**: 深灰背景，加粗文字，圆角矩形
- **condition**: 菱形或六边形，蓝色系
- **branch**: 标准圆角矩形，紫色系
- **action**: 标准圆角矩形，绿色系
- **exception**: 虚线边框，黄色系

风险等级通过节点左侧的色条/圆点区分（critical=红、high=橙、medium=黄、low=绿），与现有设计保持一致。

## 保留的业务功能映射

| 现有功能     | ReactFlow 实现方式       | simple-mind-map 实现方式                                 |
| ------------ | ------------------------ | -------------------------------------------------------- |
| 节点点击编辑 | `onNodeClick` -> Drawer  | `node_click` 事件 -> 同样打开 Drawer                     |
| 新增节点     | Modal + API              | `execCommand('INSERT_CHILD_NODE')` 或保留 Modal          |
| 删除节点     | Drawer 内按钮 + API      | `execCommand('REMOVE_NODE')` + API 同步                  |
| 折叠/展开    | 自定义 collapsedSet 管理 | 内置支持，自动处理                                       |
| 左侧目录树   | Ant Design Tree          | 保留不变，数据源相同                                     |
| 搜索高亮     | 自定义 matchedKeySet     | 保留左侧 Tree 搜索 + `renderer.highlightNode()` 画布高亮 |
| AI 解析导入  | Modal + Table 预览       | 保留不变                                                 |
| 影响提示     | Alert 组件               | 保留不变                                                 |

## 新增功能（迁移后自然获得）

- **导出功能**：工具栏增加"导出"按钮，支持 PNG / SVG / PDF / XMind / Markdown
- **主题切换**：工具栏增加主题选择器（内置多套主题）
- **快捷键操作**：Tab 添加子节点、Enter 添加兄弟节点、Delete 删除、Ctrl+Z 撤销
- **布局切换**：逻辑结构图 / 思维导图 / 组织结构图 / 鱼骨图等
- **拖拽调整**：直接拖拽节点改变父子关系
- **小地图**：内置 MiniMap 插件

## 数据同步策略

simple-mind-map 的编辑操作（拖拽、快捷键增删等）会触发 `data_change` 事件。需要设计一个同步机制：

1. **读取**：后端 `GET /tree` -> `ruleNodesToMindMapData()` -> `mindMap.setData()`
2. **画布编辑 -> 后端同步**：`data_change` 事件 -> diff 新旧数据 -> 调用对应 CRUD API -> 后端持久化
3. **Drawer 编辑 -> 画布同步**：API 更新成功 -> `reload()` -> 重新 `setData()`

diff 逻辑需要比较新旧树的节点列表，识别新增、删除、修改、移动操作，然后批量调用后端 API。这是迁移中最复杂的部分。

## 风险与注意事项

- simple-mind-map 官方示例基于 Vue，React 集成需要自行封装，但原理简单（useRef + useEffect）
- 节点自定义样式需要通过 `createNodeContent` 或主题 API 实现，可能需要一些调试
- 拖拽改变层级后的后端同步需要仔细处理（更新 parent_id + 重新 derive_rule_paths）
- reactflow 依赖如果项目其他地方没有使用，可以移除以减小包体积
