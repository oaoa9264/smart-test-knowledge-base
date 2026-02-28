import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  Edge,
  MiniMap,
  Node,
  PanOnScrollMode,
  ReactFlow,
  ReactFlowInstance,
  addEdge,
  useEdgesState,
  useNodesState,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Tree,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { aiParse, createRuleNode, deleteRuleNode, fetchRuleTree, updateRuleNode } from "../../api/rules";
import { useAppStore } from "../../stores/appStore";
import type { AIParseNode, AIParseResult, RiskLevel, RuleNode } from "../../types";
import { getNodeTypeLabel, riskLevelLabels } from "../../utils/enumLabels";

const riskOptions: { label: string; value: RiskLevel }[] = [
  { label: "严重", value: "critical" },
  { label: "高", value: "high" },
  { label: "中", value: "medium" },
  { label: "低", value: "low" },
];

const nodeTypeOptions = [
  { label: "根节点", value: "root" },
  { label: "条件", value: "condition" },
  { label: "分支", value: "branch" },
  { label: "动作", value: "action" },
  { label: "异常", value: "exception" },
];

const aiParseModeMeta: Record<
  AIParseResult["analysis_mode"],
  { label: string; alertType: "success" | "warning" | "info"; hint: string }
> = {
  llm: {
    label: "LLM",
    alertType: "success",
    hint: "当前草稿由 LLM 生成。",
  },
  mock_fallback: {
    label: "Mock（LLM降级）",
    alertType: "warning",
    hint: "LLM 不可用或返回异常，已自动降级到规则分句解析。",
  },
  mock: {
    label: "Mock",
    alertType: "info",
    hint: "当前使用规则分句解析。",
  },
};

type RuleTreeNavNode = {
  key: string;
  title: React.ReactNode;
  children?: RuleTreeNavNode[];
};

function toFlowNodes(nodes: RuleNode[], focusedNodeId: string | null): Node[] {
  const levelMap = new Map<string, number>();
  const siblings: Record<string, number> = {};

  const getDepth = (node: RuleNode, allMap: Map<string, RuleNode>): number => {
    if (!node.parent_id) return 0;
    if (levelMap.has(node.id)) return levelMap.get(node.id) || 0;
    const parent = allMap.get(node.parent_id);
    if (!parent) return 0;
    const depth = getDepth(parent, allMap) + 1;
    levelMap.set(node.id, depth);
    return depth;
  };

  const byId = new Map(nodes.map((n) => [n.id, n]));

  return nodes.map((node) => {
    const depth = getDepth(node, byId);
    const siblingKey = node.parent_id || "root";
    siblings[siblingKey] = (siblings[siblingKey] || 0) + 1;
    const order = siblings[siblingKey] - 1;
    const isFocused = focusedNodeId === node.id;

    return {
      id: node.id,
      position: { x: 220 * depth + 40, y: 110 * order + 40 },
      data: {
        label: `${node.content}`,
        ...node,
      },
      style: {
        borderRadius: 10,
        border: isFocused ? "2px solid #1677ff" : "1px solid #84a9d5",
        padding: 8,
        width: 180,
        background: isFocused ? "#eef6ff" : "#f8fcff",
        boxShadow: isFocused ? "0 0 0 2px rgba(22, 119, 255, 0.15)" : undefined,
      },
    };
  });
}

function toFlowEdges(nodes: RuleNode[]): Edge[] {
  return nodes
    .filter((n) => n.parent_id)
    .map((n) => ({
      id: `${n.parent_id}-${n.id}`,
      source: n.parent_id as string,
      target: n.id,
      animated: false,
    }));
}

function collectFocusSubgraphIds(
  focusedNodeId: string,
  nodeMap: Map<string, RuleNode>,
  childrenMap: Map<string, string[]>,
  maxChildDepth: number,
): Set<string> {
  if (!nodeMap.has(focusedNodeId)) return new Set();

  const result = new Set<string>();

  let currentId: string | null = focusedNodeId;
  while (currentId) {
    result.add(currentId);
    const currentNode = nodeMap.get(currentId);
    currentId = currentNode?.parent_id || null;
  }

  const queue: Array<{ id: string; depth: number }> = [{ id: focusedNodeId, depth: 0 }];
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) break;
    if (current.depth >= maxChildDepth) continue;
    const childIds = childrenMap.get(current.id) || [];
    childIds.forEach((childId) => {
      result.add(childId);
      queue.push({ id: childId, depth: current.depth + 1 });
    });
  }

  return result;
}

export default function RuleTreePage() {
  const { selectedRequirementId } = useAppStore();
  const [domainNodes, setDomainNodes] = useState<RuleNode[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const [showFullGraph, setShowFullGraph] = useState(false);
  const [childDepth, setChildDepth] = useState(2);
  const [treeSearch, setTreeSearch] = useState("");
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);

  const [editingNode, setEditingNode] = useState<RuleNode | null>(null);
  const [form] = Form.useForm();

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();

  const [aiOpen, setAiOpen] = useState(false);
  const [aiText, setAiText] = useState("");
  const [aiDraft, setAiDraft] = useState<AIParseNode[]>([]);
  const [aiParseMode, setAiParseMode] = useState<AIParseResult["analysis_mode"] | null>(null);

  const [lastImpact, setLastImpact] = useState<number[]>([]);

  const reload = async () => {
    if (!selectedRequirementId) {
      setDomainNodes([]);
      setNodes([]);
      setEdges([]);
      setFocusedNodeId(null);
      setExpandedKeys([]);
      return;
    }
    const tree = await fetchRuleTree(selectedRequirementId);
    setDomainNodes(tree.nodes);
  };

  useEffect(() => {
    reload().catch(() => message.error("加载规则树失败"));
  }, [selectedRequirementId]);

  useEffect(() => {
    if (!flowInstance || nodes.length === 0) return;
    const frame = requestAnimationFrame(() => {
      flowInstance.fitView({ padding: 0.2, minZoom: 0.05, duration: 200 });
    });
    return () => cancelAnimationFrame(frame);
  }, [flowInstance, nodes, edges]);

  const onConnect = useCallback(
    (params: Edge | any) => {
      setEdges((eds) => addEdge(params, eds));
    },
    [setEdges],
  );

  const nodeMap = useMemo(() => {
    const map = new Map<string, RuleNode>();
    domainNodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [domainNodes]);

  const childrenMap = useMemo(() => {
    const map = new Map<string, string[]>();
    domainNodes.forEach((node) => {
      if (!node.parent_id) return;
      const siblings = map.get(node.parent_id) || [];
      siblings.push(node.id);
      map.set(node.parent_id, siblings);
    });
    return map;
  }, [domainNodes]);

  const rootIds = useMemo(
    () =>
      domainNodes
        .filter((node) => !node.parent_id || !nodeMap.has(node.parent_id))
        .map((node) => node.id),
    [domainNodes, nodeMap],
  );

  const allNodeIds = useMemo(() => domainNodes.map((node) => node.id), [domainNodes]);

  const defaultExpandedKeys = useMemo(() => {
    const keys: string[] = [];
    const visited = new Set<string>();
    const queue = rootIds.map((id) => ({ id, depth: 0 }));

    while (queue.length > 0) {
      const current = queue.shift();
      if (!current || visited.has(current.id)) continue;
      visited.add(current.id);
      keys.push(current.id);

      if (current.depth >= 2) continue;
      const childIds = childrenMap.get(current.id) || [];
      childIds.forEach((childId) => queue.push({ id: childId, depth: current.depth + 1 }));
    }

    return keys;
  }, [childrenMap, rootIds]);

  useEffect(() => {
    if (domainNodes.length === 0) return;
    if (!focusedNodeId || !nodeMap.has(focusedNodeId)) {
      setFocusedNodeId(rootIds[0] || domainNodes[0].id);
    }
    if (expandedKeys.length === 0) {
      setExpandedKeys(defaultExpandedKeys);
    }
  }, [defaultExpandedKeys, domainNodes, expandedKeys.length, focusedNodeId, nodeMap, rootIds]);

  const matchedKeySet = useMemo(() => {
    const keyword = treeSearch.trim().toLowerCase();
    if (!keyword) return new Set<string>();

    const keys = new Set<string>();
    domainNodes.forEach((node) => {
      if (!node.content.toLowerCase().includes(keyword)) return;

      let cursor: RuleNode | undefined = node;
      while (cursor) {
        keys.add(cursor.id);
        cursor = cursor.parent_id ? nodeMap.get(cursor.parent_id) : undefined;
      }
    });

    return keys;
  }, [domainNodes, nodeMap, treeSearch]);

  useEffect(() => {
    if (!treeSearch.trim()) return;
    setExpandedKeys((prev) => Array.from(new Set([...prev, ...matchedKeySet])));
  }, [matchedKeySet, treeSearch]);

  const treeData = useMemo<RuleTreeNavNode[]>(() => {
    const built = new Set<string>();
    const buildNode = (nodeId: string, path: Set<string>): RuleTreeNavNode => {
      const node = nodeMap.get(nodeId);
      if (!node) {
        return { key: nodeId, title: nodeId };
      }

      built.add(nodeId);
      const shortText = node.content.length > 26 ? `${node.content.slice(0, 26)}...` : node.content;
      if (path.has(nodeId)) {
        return { key: nodeId, title: `${shortText} (循环)` };
      }

      const nextPath = new Set(path);
      nextPath.add(nodeId);
      const children = (childrenMap.get(nodeId) || []).map((childId) => buildNode(childId, nextPath));

      return {
        key: nodeId,
        title: <span title={node.content}>{shortText}</span>,
        children: children.length > 0 ? children : undefined,
      };
    };

    const roots = rootIds.length > 0 ? rootIds : allNodeIds;
    const data = roots.map((nodeId) => buildNode(nodeId, new Set<string>()));
    allNodeIds.forEach((nodeId) => {
      if (!built.has(nodeId)) {
        data.push(buildNode(nodeId, new Set<string>()));
      }
    });
    return data;
  }, [allNodeIds, childrenMap, nodeMap, rootIds]);

  const filteredTreeData = useMemo(() => {
    if (!treeSearch.trim()) return treeData;

    const filterNode = (node: RuleTreeNavNode): RuleTreeNavNode | null => {
      const children = (node.children || [])
        .map((child) => filterNode(child))
        .filter((child): child is RuleTreeNavNode => child !== null);
      const keepSelf = matchedKeySet.has(node.key);

      if (!keepSelf && children.length === 0) return null;
      return { ...node, children: children.length > 0 ? children : undefined };
    };

    return treeData
      .map((node) => filterNode(node))
      .filter((node): node is RuleTreeNavNode => node !== null);
  }, [matchedKeySet, treeData, treeSearch]);

  const visibleDomainNodes = useMemo(() => {
    if (showFullGraph || !focusedNodeId) return domainNodes;

    const visibleIds = collectFocusSubgraphIds(focusedNodeId, nodeMap, childrenMap, childDepth);
    if (visibleIds.size === 0) return domainNodes;
    return domainNodes.filter((node) => visibleIds.has(node.id));
  }, [childDepth, childrenMap, domainNodes, focusedNodeId, nodeMap, showFullGraph]);

  useEffect(() => {
    setNodes(toFlowNodes(visibleDomainNodes, focusedNodeId));
    setEdges(toFlowEdges(visibleDomainNodes));
  }, [focusedNodeId, setEdges, setNodes, visibleDomainNodes]);

  const onNodeClick = (_event: React.MouseEvent, node: Node) => {
    const domainNode = nodeMap.get(node.id);
    if (!domainNode) return;
    setFocusedNodeId(node.id);
    setShowFullGraph(false);
    setEditingNode(domainNode);
    form.setFieldsValue(domainNode);
  };

  const handleSaveNode = async () => {
    if (!editingNode) return;
    const values = await form.validateFields();
    const resp = await updateRuleNode(editingNode.id, values);
    setLastImpact(resp.impact.needs_review_case_ids);
    message.success("节点已更新");
    setEditingNode(null);
    await reload();
  };

  const handleDeleteNode = async () => {
    if (!editingNode) return;
    const resp = await deleteRuleNode(editingNode.id);
    setLastImpact(resp.impact.needs_review_case_ids);
    message.success("节点已删除");
    setEditingNode(null);
    await reload();
  };

  const handleCreateNode = async () => {
    if (!selectedRequirementId) {
      message.warning("请先选择需求");
      return;
    }
    const values = await createForm.validateFields();
    await createRuleNode({
      requirement_id: selectedRequirementId,
      parent_id: values.parent_id || null,
      node_type: values.node_type,
      content: values.content,
      risk_level: values.risk_level,
    });
    setCreateOpen(false);
    createForm.resetFields();
    message.success("节点已创建");
    await reload();
  };

  const runAIParse = async () => {
    const result = await aiParse(aiText);
    setAiDraft(result.nodes);
    setAiParseMode(result.analysis_mode);
  };

  const importAIDraft = async () => {
    if (!selectedRequirementId) {
      message.warning("请先选择需求");
      return;
    }
    const idMap = new Map<string, string>();

    for (const draft of aiDraft) {
      const parentId = draft.parent_id ? idMap.get(draft.parent_id) || null : null;
      const created = await createRuleNode({
        requirement_id: selectedRequirementId,
        parent_id: parentId,
        node_type: draft.type,
        content: draft.content,
        risk_level: draft.type === "root" ? "high" : "medium",
      });
      idMap.set(draft.id, created.id);
    }

    message.success("AI 草稿已导入");
    setAiOpen(false);
    setAiText("");
    setAiDraft([]);
    setAiParseMode(null);
    await reload();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 150px)" }}>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" onClick={() => setCreateOpen(true)}>
          新增节点
        </Button>
        <Button onClick={() => setAiOpen(true)}>AI 半自动解析 (P1)</Button>
      </Space>

      {lastImpact.length > 0 && (
        <Alert
          style={{ marginBottom: 12 }}
          type="warning"
          message={`变更影响: ${lastImpact.length} 条用例已标记为待复核 (${lastImpact.join(", ")})`}
        />
      )}

      {!selectedRequirementId ? (
        <Alert type="info" message="请先在顶部选择需求" />
      ) : (
        <div style={{ flex: 1, display: "flex", gap: 12, minHeight: 0 }}>
          <div
            style={{
              width: 320,
              border: "1px solid #d7e2ee",
              borderRadius: 10,
              padding: 10,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <Typography.Text strong style={{ marginBottom: 8 }}>
              规则目录
            </Typography.Text>
            <Input.Search
              placeholder="搜索节点内容"
              allowClear
              value={treeSearch}
              onChange={(event) => setTreeSearch(event.target.value)}
            />
            <Space style={{ marginTop: 8, marginBottom: 8 }}>
              <Button size="small" onClick={() => setExpandedKeys(allNodeIds)}>
                展开全部
              </Button>
              <Button size="small" onClick={() => setExpandedKeys(rootIds)}>
                仅根节点
              </Button>
            </Space>
            <Typography.Text type="secondary" style={{ marginBottom: 8 }}>
              总节点 {domainNodes.length}，当前展示 {visibleDomainNodes.length}
            </Typography.Text>
            <div
              style={{
                flex: 1,
                minHeight: 0,
                overflow: "auto",
                border: "1px solid #eef2f7",
                borderRadius: 8,
                padding: 6,
              }}
            >
              <Tree
                blockNode
                showLine
                selectedKeys={focusedNodeId ? [focusedNodeId] : []}
                expandedKeys={expandedKeys}
                onExpand={(keys) => setExpandedKeys(keys as string[])}
                onSelect={(keys) => {
                  const selectedId = keys[0] as string | undefined;
                  if (!selectedId) return;
                  setFocusedNodeId(selectedId);
                  setShowFullGraph(false);
                }}
                treeData={filteredTreeData}
              />
            </div>
          </div>
          <div
            style={{
              flex: 1,
              minWidth: 0,
              border: "1px solid #d7e2ee",
              borderRadius: 10,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ padding: 10, borderBottom: "1px solid #eef2f7" }}>
              <Space wrap>
                <Typography.Text>
                  {showFullGraph
                    ? "当前：全图视图"
                    : `焦点节点：${focusedNodeId ? nodeMap.get(focusedNodeId)?.content || focusedNodeId : "-"}`}
                </Typography.Text>
                <Select
                  size="small"
                  value={childDepth}
                  disabled={showFullGraph || !focusedNodeId}
                  onChange={(value) => setChildDepth(value)}
                  options={[
                    { label: "子节点 0 层", value: 0 },
                    { label: "子节点 1 层", value: 1 },
                    { label: "子节点 2 层", value: 2 },
                    { label: "子节点 3 层", value: 3 },
                    { label: "子节点 4 层", value: 4 },
                  ]}
                />
                <Button
                  size="small"
                  onClick={() => setShowFullGraph((prev) => !prev)}
                  disabled={!focusedNodeId && !showFullGraph}
                >
                  {showFullGraph ? "切回焦点视图" : "查看全图"}
                </Button>
              </Space>
            </div>
            <div style={{ flex: 1 }}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={onNodeClick}
                onInit={setFlowInstance}
                panOnDrag
                panOnScroll
                panOnScrollMode={PanOnScrollMode.Free}
                fitView
                fitViewOptions={{ padding: 0.2, minZoom: 0.05 }}
                minZoom={0.05}
              >
                <Background gap={14} size={1} />
                <Controls />
                <MiniMap />
              </ReactFlow>
            </div>
          </div>
        </div>
      )}

      <Drawer open={!!editingNode} title="编辑规则节点" onClose={() => setEditingNode(null)} width={420}>
        <Form layout="vertical" form={form}>
          <Form.Item name="content" label="节点内容" rules={[{ required: true }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="node_type" label="节点类型" rules={[{ required: true }]}>
            <Select options={nodeTypeOptions} />
          </Form.Item>
          <Form.Item name="risk_level" label="风险等级" rules={[{ required: true }]}>
            <Select options={riskOptions} />
          </Form.Item>
          <Space>
            <Button type="primary" onClick={handleSaveNode}>
              保存
            </Button>
            <Button danger onClick={handleDeleteNode}>
              删除节点
            </Button>
          </Space>
        </Form>
      </Drawer>

      <Modal title="新增规则节点" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={handleCreateNode}>
        <Form layout="vertical" form={createForm}>
          <Form.Item name="content" label="内容" rules={[{ required: true, message: "请输入内容" }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="node_type" label="类型" initialValue="condition" rules={[{ required: true }]}>
            <Select options={nodeTypeOptions} />
          </Form.Item>
          <Form.Item name="risk_level" label="风险等级" initialValue="medium" rules={[{ required: true }]}>
            <Select options={riskOptions} />
          </Form.Item>
          <Form.Item name="parent_id" label="父节点 (可选)">
            <Select allowClear options={domainNodes.map((n) => ({ value: n.id, label: n.content }))} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="AI 半自动解析需求"
        open={aiOpen}
        onCancel={() => {
          setAiOpen(false);
          setAiParseMode(null);
        }}
        onOk={importAIDraft}
        okText="确认导入"
        width={840}
      >
        <Typography.Paragraph type="secondary">
          输入 PRD 片段，系统先返回草稿节点，你确认后再导入正式规则树。
        </Typography.Paragraph>
        <Input.TextArea
          rows={5}
          value={aiText}
          onChange={(e) => setAiText(e.target.value)}
          placeholder="例如：如果用户未实名认证，则禁止提现；如果实名认证且余额充足，则允许提现"
        />
        <div style={{ marginTop: 10, marginBottom: 10 }}>
          <Button onClick={runAIParse} disabled={!aiText.trim()}>
            生成草稿
          </Button>
        </div>
        {aiParseMode && (
          <Alert
            style={{ marginBottom: 10 }}
            type={aiParseModeMeta[aiParseMode].alertType}
            message={`解析引擎：${aiParseModeMeta[aiParseMode].label}`}
            description={aiParseModeMeta[aiParseMode].hint}
            showIcon
          />
        )}
        <Table
          size="small"
          rowKey="id"
          dataSource={aiDraft}
          pagination={false}
          columns={[
            { title: "临时ID", dataIndex: "id", width: 120 },
            { title: "类型", dataIndex: "type", render: (v) => <Tag>{getNodeTypeLabel(v)}</Tag>, width: 120 },
            { title: "内容", dataIndex: "content" },
            { title: "父节点", dataIndex: "parent_id", width: 120 },
            {
              title: "默认风险",
              render: (_, row) => (
                <Tag>{riskLevelLabels[row.type === "root" ? "high" : "medium"]}</Tag>
              ),
              width: 120,
            },
          ]}
        />
      </Modal>
    </div>
  );
}
