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
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { aiParse, createRuleNode, deleteRuleNode, fetchRuleTree, updateRuleNode } from "../../api/rules";
import { useAppStore } from "../../stores/appStore";
import type { AIParseNode, RiskLevel, RuleNode } from "../../types";
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

function toFlowNodes(nodes: RuleNode[]): Node[] {
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

    return {
      id: node.id,
      position: { x: 220 * depth + 40, y: 110 * order + 40 },
      data: {
        label: `${node.content}`,
        ...node,
      },
      style: {
        borderRadius: 10,
        border: "1px solid #84a9d5",
        padding: 8,
        width: 180,
        background: "#f8fcff",
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

export default function RuleTreePage() {
  const { selectedRequirementId } = useAppStore();
  const [domainNodes, setDomainNodes] = useState<RuleNode[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null);

  const [editingNode, setEditingNode] = useState<RuleNode | null>(null);
  const [form] = Form.useForm();

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();

  const [aiOpen, setAiOpen] = useState(false);
  const [aiText, setAiText] = useState("");
  const [aiDraft, setAiDraft] = useState<AIParseNode[]>([]);

  const [lastImpact, setLastImpact] = useState<number[]>([]);

  const reload = async () => {
    if (!selectedRequirementId) {
      setDomainNodes([]);
      setNodes([]);
      setEdges([]);
      return;
    }
    const tree = await fetchRuleTree(selectedRequirementId);
    setDomainNodes(tree.nodes);
    setNodes(toFlowNodes(tree.nodes));
    setEdges(toFlowEdges(tree.nodes));
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

  const onNodeClick = (_event: React.MouseEvent, node: Node) => {
    const domainNode = nodeMap.get(node.id);
    if (!domainNode) return;
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
        <div style={{ flex: 1, border: "1px solid #d7e2ee", borderRadius: 10 }}>
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
        onCancel={() => setAiOpen(false)}
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
