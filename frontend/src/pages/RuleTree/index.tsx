import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tree,
  Typography,
  message,
} from "antd";
import { aiParse, createRuleNode, deleteRuleNode, fetchRuleTree, updateRuleNode } from "../../api/rules";
import { useAppStore } from "../../stores/appStore";
import type { AIParseNode, AIParseResult, RiskLevel, RuleNode } from "../../types";
import { getNodeTypeLabel, riskLevelLabels } from "../../utils/enumLabels";
import type { MindMapTreeNode } from "./dataAdapter";
import { mindMapDataToRuleNodes, normalizeRuleNodeContent, ruleNodesToMindMapData } from "./dataAdapter";
import MindMapWrapper, { type MindMapExportType, type MindMapWrapperRef } from "./MindMapWrapper";
import { RULE_TREE_THEME } from "./mindMapTheme";

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

export default function RuleTreePage() {
  const { selectedRequirementId } = useAppStore();
  const [domainNodes, setDomainNodes] = useState<RuleNode[]>([]);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const [treeSearch, setTreeSearch] = useState("");
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);

  const layout = "organizationStructure";
  const theme = RULE_TREE_THEME;
  const [textAutoWrapWidth, setTextAutoWrapWidth] = useState<number>(150);

  const [editingNode, setEditingNode] = useState<RuleNode | null>(null);
  const [form] = Form.useForm();

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();

  const [aiOpen, setAiOpen] = useState(false);
  const [aiText, setAiText] = useState("");
  const [aiDraft, setAiDraft] = useState<AIParseNode[]>([]);
  const [aiParseMode, setAiParseMode] = useState<AIParseResult["analysis_mode"] | null>(null);

  const [lastImpact, setLastImpact] = useState<number[]>([]);

  const mindMapRef = useRef<MindMapWrapperRef | null>(null);
  const canvasSyncTimerRef = useRef<number | null>(null);
  const isCanvasSyncingRef = useRef(false);
  const pendingCanvasTreeRef = useRef<MindMapTreeNode | null>(null);
  const domainNodesRef = useRef<RuleNode[]>([]);

  const reload = async () => {
    if (!selectedRequirementId) {
      domainNodesRef.current = [];
      setDomainNodes([]);
      setFocusedNodeId(null);
      setExpandedKeys([]);
      return;
    }

    const tree = await fetchRuleTree(selectedRequirementId);
    const normalizedNodes = tree.nodes.map((node) => ({
      ...node,
      content: normalizeRuleNodeContent(node.content),
    }));
    domainNodesRef.current = normalizedNodes;
    setDomainNodes(normalizedNodes);
  };

  useEffect(() => {
    domainNodesRef.current = domainNodes;
  }, [domainNodes]);

  useEffect(() => {
    setExpandedKeys([]);
    setFocusedNodeId(null);
    reload().catch(() => message.error("加载规则树失败"));
  }, [selectedRequirementId]);

  useEffect(() => {
    return () => {
      if (canvasSyncTimerRef.current) {
        window.clearTimeout(canvasSyncTimerRef.current);
      }
      pendingCanvasTreeRef.current = null;
    };
  }, []);

  const nodeMap = useMemo(() => {
    const map = new Map<string, RuleNode>();
    domainNodes.forEach((node) => map.set(node.id, node));
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
    if (!treeSearch.trim()) {
      mindMapRef.current?.clearHighlight();
      return;
    }

    setExpandedKeys((prev) => Array.from(new Set([...prev, ...matchedKeySet])));

    const firstMatch = domainNodes.find((node) => matchedKeySet.has(node.id));
    if (firstMatch) {
      mindMapRef.current?.highlightNode(firstMatch.id);
    }
  }, [domainNodes, matchedKeySet, treeSearch]);

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

  const mindMapData = useMemo(() => ruleNodesToMindMapData(domainNodes), [domainNodes]);

  const onMindMapNodeClick = useCallback(
    (nodeId: string) => {
      const domainNode = nodeMap.get(nodeId);
      if (!domainNode) return;

      setFocusedNodeId(nodeId);
      setEditingNode(domainNode);
      form.setFieldsValue(domainNode);
    },
    [form, nodeMap],
  );

  const syncCanvasChanges = useCallback(
    (nextTree: MindMapTreeNode) => {
      if (!selectedRequirementId) return;
      pendingCanvasTreeRef.current = nextTree;

      if (canvasSyncTimerRef.current) {
        window.clearTimeout(canvasSyncTimerRef.current);
      }

      canvasSyncTimerRef.current = window.setTimeout(async () => {
        if (isCanvasSyncingRef.current) return;
        const treeToSync = pendingCanvasTreeRef.current;
        if (!treeToSync) return;
        pendingCanvasTreeRef.current = null;

        const currentDomainNodes = domainNodesRef.current;
        const nextNodes = mindMapDataToRuleNodes(treeToSync);
        const prevNodeMap = new Map(currentDomainNodes.map((node) => [node.id, node]));
        const nextNodeMap = new Map(nextNodes.map((node) => [node.id, node]));

        const added = nextNodes.filter((node) => !prevNodeMap.has(node.id));
        const removed = currentDomainNodes.filter((node) => !nextNodeMap.has(node.id));
        const addedPending = new Map(added.map((node) => [node.id, node]));
        const tempIdToRealId = new Map<string, string>();
        const resolveParentId = (parentId: string | null): string | null => {
          if (!parentId) return null;
          return tempIdToRealId.get(parentId) || parentId;
        };

        const updates = nextNodes
          .map((node) => {
            const prev = prevNodeMap.get(node.id);
            if (!prev) return null;

            const payload: {
              parent_id?: string | null;
              node_type?: string;
              content?: string;
              risk_level?: string;
            } = {};

            if (prev.parent_id !== node.parent_id) payload.parent_id = node.parent_id;
            if (prev.node_type !== node.node_type) payload.node_type = node.node_type;
            if (prev.content !== node.content) payload.content = node.content;
            if (prev.risk_level !== node.risk_level) payload.risk_level = node.risk_level;

            if (Object.keys(payload).length === 0) return null;
            return { nodeId: node.id, payload };
          })
          .filter(
            (
              item,
            ): item is {
              nodeId: string;
              payload: {
                parent_id?: string | null;
                node_type?: string;
                content?: string;
                risk_level?: string;
              };
            } => item !== null,
          );

        const hasAnyChange = added.length > 0 || removed.length > 0 || updates.length > 0;
        if (!hasAnyChange) return;

        isCanvasSyncingRef.current = true;
        try {
          const impactSet = new Set<number>();

          // 1) 先创建新增节点（处理新增节点之间的父子依赖）
          while (addedPending.size > 0) {
            let progressed = false;

            for (const [tempId, node] of Array.from(addedPending.entries())) {
              const rawParentId = node.parent_id;
              const parentIsExisting = !!rawParentId && prevNodeMap.has(rawParentId);
              const parentIsCreated = !!rawParentId && tempIdToRealId.has(rawParentId);
              const parentInPending = !!rawParentId && addedPending.has(rawParentId);
              const isRoot = !rawParentId;

              if (!isRoot && !parentIsExisting && !parentIsCreated && !parentInPending) {
                continue;
              }
              if (parentInPending && !parentIsCreated) {
                continue;
              }

              const created = await createRuleNode({
                requirement_id: selectedRequirementId,
                parent_id: resolveParentId(rawParentId),
                node_type: node.node_type,
                content: node.content,
                risk_level: node.risk_level,
              });
              tempIdToRealId.set(tempId, created.id);
              addedPending.delete(tempId);
              progressed = true;
            }

            if (!progressed) {
              throw new Error("新增节点存在无法解析的父子关系");
            }
          }

          // 2) 同步已有节点修改
          for (const update of updates) {
            const prev = prevNodeMap.get(update.nodeId);
            if (!prev) continue;

            const normalizedPayload = { ...update.payload };
            if (Object.prototype.hasOwnProperty.call(normalizedPayload, "parent_id")) {
              normalizedPayload.parent_id = resolveParentId(normalizedPayload.parent_id ?? null);
            }

            if (
              (normalizedPayload.parent_id ?? prev.parent_id) === prev.parent_id &&
              (normalizedPayload.node_type ?? prev.node_type) === prev.node_type &&
              (normalizedPayload.content ?? prev.content) === prev.content &&
              (normalizedPayload.risk_level ?? prev.risk_level) === prev.risk_level
            ) {
              continue;
            }

            const resp = await updateRuleNode(update.nodeId, normalizedPayload);
            resp.impact.needs_review_case_ids.forEach((id) => impactSet.add(id));
          }

          // 3) 删除在画布中被移除的节点
          for (const removedNode of removed) {
            const resp = await deleteRuleNode(removedNode.id);
            resp.impact.needs_review_case_ids.forEach((id) => impactSet.add(id));
          }

          setLastImpact(Array.from(impactSet));
          message.success(
            `画布变更已同步（新增 ${added.length} / 更新 ${updates.length} / 删除 ${removed.length}）`,
          );
          await reload();
        } catch {
          message.error("画布变更同步失败，已刷新回服务端最新数据");
          await reload();
        } finally {
          isCanvasSyncingRef.current = false;
          if (pendingCanvasTreeRef.current) {
            syncCanvasChanges(pendingCanvasTreeRef.current);
          }
        }
      }, 420);
    },
    [selectedRequirementId],
  );

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

  const handleExport = async (type: MindMapExportType) => {
    try {
      await mindMapRef.current?.exportAs(type, "规则树");
      message.success(`导出 ${type.toUpperCase()} 成功`);
    } catch {
      message.error("导出失败，请重试");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 150px)" }}>
      <Space style={{ marginBottom: 12 }} wrap>
        <Button type="primary" onClick={() => setCreateOpen(true)}>
          新增节点
        </Button>
        <Button onClick={() => setAiOpen(true)}>AI 半自动解析 (P1)</Button>
        <Space size={6}>
          <Typography.Text type="secondary">文本宽度</Typography.Text>
          <InputNumber
            min={80}
            max={800}
            step={10}
            value={textAutoWrapWidth}
            onChange={(value) => setTextAutoWrapWidth(typeof value === "number" ? value : 150)}
            style={{ width: 100 }}
          />
        </Space>

        <Button onClick={() => mindMapRef.current?.fitView()}>适应画布</Button>
        <Button onClick={() => handleExport("png")}>导出 PNG</Button>
        <Button onClick={() => handleExport("svg")}>导出 SVG</Button>
        <Button onClick={() => handleExport("xmind")}>导出 XMind</Button>
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
              总节点 {domainNodes.length}
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
                  mindMapRef.current?.focusNode(selectedId);
                  mindMapRef.current?.highlightNode(selectedId);
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
              <Typography.Text>
                当前选中：{focusedNodeId ? nodeMap.get(focusedNodeId)?.content || focusedNodeId : "-"}
              </Typography.Text>
            </div>
            <div style={{ flex: 1 }}>
              <MindMapWrapper
                ref={mindMapRef}
                data={mindMapData}
                selectedNodeId={focusedNodeId}
                layout={layout}
                theme={theme}
                editable
                textAutoWrapWidth={textAutoWrapWidth}
                onNodeClick={onMindMapNodeClick}
                onDataChange={syncCanvasChanges}
              />
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
            <Select allowClear options={domainNodes.map((node) => ({ value: node.id, label: node.content }))} />
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
          onChange={(event) => setAiText(event.target.value)}
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
            { title: "类型", dataIndex: "type", render: (value) => <Tag>{getNodeTypeLabel(value)}</Tag>, width: 120 },
            { title: "内容", dataIndex: "content" },
            { title: "父节点", dataIndex: "parent_id", width: 120 },
            {
              title: "默认风险",
              render: (_, row) => <Tag>{riskLevelLabels[row.type === "root" ? "high" : "medium"]}</Tag>,
              width: 120,
            },
          ]}
        />
      </Modal>
    </div>
  );
}
