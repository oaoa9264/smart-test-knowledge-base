import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Divider,
  Drawer,
  Dropdown,
  Form,
  Input,
  InputNumber,
  List,
  Menu,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Steps,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Tree,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { CheckCircleOutlined, CloseOutlined, DeleteOutlined, DownOutlined, EditOutlined, ExperimentOutlined, HistoryOutlined, InboxOutlined, PlusOutlined, RobotOutlined, SaveOutlined, WarningOutlined } from "@ant-design/icons";
import { getErrorMessage } from "../../api/client";
import {
  generateTestPlan,
  generateTestCases,
  confirmTestCases,
  getTestPlanSessions,
  createTestPlanSession,
  archiveTestPlanSession,
  updateSessionCases,
  updateTestPlan,
} from "../../api/testPlan";
import { createNewVersion, fetchRequirementVersions, fetchRequirements } from "../../api/projects";
import { fetchRisks } from "../../api/risks";
import {
  confirmRuleTreeSession,
  createRuleTreeSession,
  fetchRuleTreeSessionDetail,
  fetchRuleTreeSessions,
  generateRuleTreeSession,
  updateRuleTreeSession,
} from "../../api/ruleTreeSession";
import { createRuleNode, deleteRuleNode, fetchRuleTree, updateRuleNode } from "../../api/rules";
import { deleteDiffRecord, fetchDiffHistory, fetchSemanticDiff } from "../../api/treeDiff";
import { useAppStore } from "../../stores/appStore";
import type {
  DiffRecordRead,
  GeneratedTestCase,
  RuleTreeSession,
  RuleTreeSessionDetail,
  RuleTreeSessionGenerateResult,
  RuleTreeSessionUpdateResult,
  RequirementVersion,
  RiskItem,
  RiskLevel,
  RuleNode,
  SemanticDiffResult,
  TestPlanSession,
  TestPoint,
} from "../../types";
import type { MindMapTreeNode } from "./dataAdapter";
import { buildNodeRiskMap, mindMapDataToRuleNodes, normalizeRuleNodeContent, ruleNodesToMindMapData } from "./dataAdapter";
import MindMapWrapper, { type MindMapExportType, type MindMapWrapperRef } from "./MindMapWrapper";
import { RULE_TREE_THEME } from "./mindMapTheme";
import RiskPanel from "./RiskPanel";

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

type RuleTreeNavNode = {
  key: string;
  title: React.ReactNode;
  children?: RuleTreeNavNode[];
};

function DiffResultDisplay({ result }: { result: SemanticDiffResult }) {
  return (
    <>
      <Alert
        style={{ marginBottom: 12 }}
        type="info"
        message={`对比总结（v${result.base_version} → v${result.compare_version}）`}
        description={
          <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>
            {result.summary}
          </Typography.Paragraph>
        }
        showIcon
      />

      {result.risk_notes && (
        <Alert
          style={{ marginBottom: 12 }}
          type="warning"
          message="风险提示"
          description={result.risk_notes}
          showIcon
        />
      )}

      {result.flow_changes.length === 0 ? (
        <Alert style={{ marginBottom: 12 }} type="success" message="两个版本无实质性流程差异" />
      ) : (
        <Table
          size="small"
          rowKey={(_, index) => String(index)}
          dataSource={result.flow_changes}
          pagination={false}
          expandable={{
            expandedRowRender: (record) =>
              record.detail ? (
                <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>
                  {record.detail}
                </Typography.Paragraph>
              ) : (
                <Typography.Text type="secondary">无详细说明</Typography.Text>
              ),
            rowExpandable: (record) => !!record.detail,
          }}
          columns={[
            {
              title: "变更类型",
              dataIndex: "change_type",
              width: 100,
              render: (type: string) => {
                const meta: Record<string, { color: string; label: string }> = {
                  added: { color: "green", label: "新增" },
                  removed: { color: "red", label: "删除" },
                  modified: { color: "orange", label: "修改" },
                };
                const m = meta[type] || { color: "default", label: type };
                return <Tag color={m.color}>{m.label}</Tag>;
              },
            },
            {
              title: "变更描述",
              dataIndex: "description",
            },
            {
              title: "影响程度",
              dataIndex: "impact",
              width: 100,
              render: (impact: string) => {
                const meta: Record<string, { color: string; label: string }> = {
                  high: { color: "red", label: "高" },
                  medium: { color: "orange", label: "中" },
                  low: { color: "blue", label: "低" },
                };
                const m = meta[impact] || { color: "default", label: impact };
                return <Tag color={m.color}>{m.label}</Tag>;
              },
            },
          ]}
        />
      )}
    </>
  );
}

export default function RuleTreePage() {
  const {
    selectedProjectId,
    selectedRequirementId,
    requirements,
    setRequirements,
    setSelectedRequirementId,
  } = useAppStore();
  const [activeRequirementId, setActiveRequirementId] = useState<number | null>(selectedRequirementId);
  const [versions, setVersions] = useState<RequirementVersion[]>([]);
  const [versionLoading, setVersionLoading] = useState(false);
  const [diffOpen, setDiffOpen] = useState(false);
  const [baseVersionRequirementId, setBaseVersionRequirementId] = useState<number>();
  const [compareVersionRequirementId, setCompareVersionRequirementId] = useState<number>();
  const [diffLoading, setDiffLoading] = useState(false);
  const [semanticDiffResult, setSemanticDiffResult] = useState<SemanticDiffResult | null>(null);
  const [diffHistory, setDiffHistory] = useState<DiffRecordRead[]>([]);
  const [diffHistoryLoading, setDiffHistoryLoading] = useState(false);
  const [diffActiveTab, setDiffActiveTab] = useState<string>("new");
  const [viewingHistoryResult, setViewingHistoryResult] = useState<SemanticDiffResult | null>(null);
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

  const [sessionPanelOpen, setSessionPanelOpen] = useState(false);
  const [showSessionUpdate, setShowSessionUpdate] = useState(false);
  const [showSessionHistory, setShowSessionHistory] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionUpdateLoading, setSessionUpdateLoading] = useState(false);
  const [sessionConfirmLoading, setSessionConfirmLoading] = useState(false);
  const [sessions, setSessions] = useState<RuleTreeSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<number>();
  const [sessionDetail, setSessionDetail] = useState<RuleTreeSessionDetail | null>(null);
  const [sessionRequirementText, setSessionRequirementText] = useState("");
  const [sessionTitleInput, setSessionTitleInput] = useState("");
  const [sessionUpdateText, setSessionUpdateText] = useState("");
  const [sessionGenerateResult, setSessionGenerateResult] = useState<RuleTreeSessionGenerateResult | null>(null);
  const [sessionUpdateResult, setSessionUpdateResult] = useState<RuleTreeSessionUpdateResult | null>(null);
  const [sessionConfirmed, setSessionConfirmed] = useState(false);
  const [sessionImageFile, setSessionImageFile] = useState<UploadFile[]>([]);

  const [lastImpact, setLastImpact] = useState<number[]>([]);
  const [riskItems, setRiskItems] = useState<RiskItem[]>([]);
  const [riskPanelVisible, setRiskPanelVisible] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId: string } | null>(null);

  const [testPlanDrawerOpen, setTestPlanDrawerOpen] = useState(false);
  const [testPlanStep, setTestPlanStep] = useState(0);
  const [testPlanLoading, setTestPlanLoading] = useState(false);
  const [testCaseGenLoading, setTestCaseGenLoading] = useState(false);
  const [testCaseConfirmLoading, setTestCaseConfirmLoading] = useState(false);
  const [testPlanMarkdown, setTestPlanMarkdown] = useState("");
  const [testPlanPoints, setTestPlanPoints] = useState<TestPoint[]>([]);
  const [generatedCases, setGeneratedCases] = useState<GeneratedTestCase[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null);
  const [currentSessionConfirmed, setCurrentSessionConfirmed] = useState(false);
  const [testPlanSessionLoading, setTestPlanSessionLoading] = useState(false);
  const [sessionCreatedAt, setSessionCreatedAt] = useState<string | null>(null);
  const [historySessions, setHistorySessions] = useState<TestPlanSession[]>([]);
  const [isEditingPlan, setIsEditingPlan] = useState(false);
  const [editingMarkdown, setEditingMarkdown] = useState("");
  const [editingPoints, setEditingPoints] = useState<TestPoint[]>([]);
  const [planSaveLoading, setPlanSaveLoading] = useState(false);
  const [editingPointModalOpen, setEditingPointModalOpen] = useState(false);
  const [editingPointIndex, setEditingPointIndex] = useState<number | null>(null);
  const [editingPointForm] = Form.useForm();

  const mindMapRef = useRef<MindMapWrapperRef | null>(null);
  const canvasSyncTimerRef = useRef<number | null>(null);
  const canvasSyncSuppressTimerRef = useRef<number | null>(null);
  const isCanvasSyncingRef = useRef(false);
  const suppressCanvasSyncRef = useRef(false);
  const pendingCanvasTreeRef = useRef<MindMapTreeNode | null>(null);
  const domainNodesRef = useRef<RuleNode[]>([]);
  const activeRequirementIdRef = useRef<number | null>(activeRequirementId);

  const beginSuppressCanvasSync = useCallback((durationMs: number = 800) => {
    suppressCanvasSyncRef.current = true;
    if (canvasSyncSuppressTimerRef.current) {
      window.clearTimeout(canvasSyncSuppressTimerRef.current);
    }
    canvasSyncSuppressTimerRef.current = window.setTimeout(() => {
      suppressCanvasSyncRef.current = false;
      canvasSyncSuppressTimerRef.current = null;
    }, durationMs);
  }, []);

  const switchRequirement = useCallback(
    (nextRequirementId: number | null) => {
      beginSuppressCanvasSync(1200);
      if (canvasSyncTimerRef.current) {
        window.clearTimeout(canvasSyncTimerRef.current);
        canvasSyncTimerRef.current = null;
      }
      pendingCanvasTreeRef.current = null;
      isCanvasSyncingRef.current = false;
      domainNodesRef.current = [];
      setDomainNodes([]);
      setFocusedNodeId(null);
      setExpandedKeys([]);
      setActiveRequirementId(nextRequirementId);
    },
    [beginSuppressCanvasSync],
  );

  const reload = useCallback(async (targetRequirementId?: number | null) => {
    const requirementId = targetRequirementId ?? activeRequirementIdRef.current;
    if (!requirementId) {
      beginSuppressCanvasSync();
      domainNodesRef.current = [];
      setDomainNodes([]);
      setFocusedNodeId(null);
      setExpandedKeys([]);
      setRiskItems([]);
      return;
    }

    const [tree, risksResp] = await Promise.all([
      fetchRuleTree(requirementId),
      fetchRisks(requirementId).catch(() => ({ risks: [] as RiskItem[] })),
    ]);
    if (activeRequirementIdRef.current !== requirementId) {
      return;
    }
    beginSuppressCanvasSync();
    const normalizedNodes = tree.nodes.map((node) => ({
      ...node,
      content: normalizeRuleNodeContent(node.content),
    }));
    domainNodesRef.current = normalizedNodes;
    setDomainNodes(normalizedNodes);
    setRiskItems(risksResp.risks);
  }, [beginSuppressCanvasSync]);

  useEffect(() => {
    domainNodesRef.current = domainNodes;
  }, [domainNodes]);

  useEffect(() => {
    switchRequirement(selectedRequirementId);
  }, [selectedRequirementId, switchRequirement]);

  useEffect(() => {
    activeRequirementIdRef.current = activeRequirementId;
  }, [activeRequirementId]);

  const reloadVersions = useCallback(
    async (targetRequirementId: number) => {
      if (!selectedProjectId || !targetRequirementId) {
        setVersions([]);
        return;
      }

      setVersionLoading(true);
      try {
        const data = await fetchRequirementVersions(selectedProjectId, targetRequirementId);
        setVersions(data);
      } finally {
        setVersionLoading(false);
      }
    },
    [selectedProjectId],
  );

  useEffect(() => {
    if (!selectedProjectId || !selectedRequirementId) {
      setVersions([]);
      return;
    }
    reloadVersions(selectedRequirementId).catch(() => message.error("加载版本列表失败"));
  }, [reloadVersions, selectedProjectId, selectedRequirementId]);

  const reloadSessions = useCallback(
    async (requirementId: number) => {
      if (!requirementId) {
        setSessions([]);
        setSelectedSessionId(undefined);
        return;
      }
      const data = await fetchRuleTreeSessions(requirementId);
      setSessions(data);
      if (!data.length) {
        setSelectedSessionId(undefined);
        return;
      }
      setSelectedSessionId((prev) => (prev && data.some((item) => item.id === prev) ? prev : data[0].id));
    },
    [],
  );

  useEffect(() => {
    if (!activeRequirementId) {
      setSessions([]);
      setSelectedSessionId(undefined);
      return;
    }
    reloadSessions(activeRequirementId).catch((error) => message.error(getErrorMessage(error, "加载会话失败")));
  }, [activeRequirementId, reloadSessions]);

  useEffect(() => {
    setSessionConfirmed(false);
    if (!selectedSessionId) {
      setSessionDetail(null);
      return;
    }
    fetchRuleTreeSessionDetail(selectedSessionId)
      .then(setSessionDetail)
      .catch((error) => message.error(getErrorMessage(error, "加载会话详情失败")));
  }, [selectedSessionId]);

  useEffect(() => {
    if (canvasSyncTimerRef.current) {
      window.clearTimeout(canvasSyncTimerRef.current);
      canvasSyncTimerRef.current = null;
    }
    beginSuppressCanvasSync();
    pendingCanvasTreeRef.current = null;
    isCanvasSyncingRef.current = false;
    domainNodesRef.current = [];
    setDomainNodes([]);
    setExpandedKeys([]);
    setFocusedNodeId(null);
    reload(activeRequirementId).catch(() => message.error("加载规则树失败"));
  }, [activeRequirementId, beginSuppressCanvasSync, reload]);

  useEffect(() => {
    return () => {
      if (canvasSyncTimerRef.current) {
        window.clearTimeout(canvasSyncTimerRef.current);
      }
      if (canvasSyncSuppressTimerRef.current) {
        window.clearTimeout(canvasSyncSuppressTimerRef.current);
      }
      pendingCanvasTreeRef.current = null;
      suppressCanvasSyncRef.current = false;
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

  const latestVersionRequirementId = useMemo(
    () => (versions.length > 0 ? versions[versions.length - 1].id : activeRequirementId),
    [activeRequirementId, versions],
  );
  const isReadonlyVersion = !!activeRequirementId && !!latestVersionRequirementId && activeRequirementId !== latestVersionRequirementId;

  useEffect(() => {
    if (domainNodes.length === 0) return;

    if (!focusedNodeId || !nodeMap.has(focusedNodeId)) {
      setFocusedNodeId(rootIds[0] || domainNodes[0].id);
    }

    if (expandedKeys.length === 0) {
      setExpandedKeys(defaultExpandedKeys);
    }
  }, [defaultExpandedKeys, domainNodes, expandedKeys.length, focusedNodeId, nodeMap, rootIds]);

  useEffect(() => {
    if (!isReadonlyVersion) return;
    setEditingNode(null);
    setCreateOpen(false);
  }, [isReadonlyVersion]);

  useEffect(() => {
    if (!versions.length) {
      setBaseVersionRequirementId(undefined);
      setCompareVersionRequirementId(undefined);
      return;
    }
    if (versions.length === 1) {
      setBaseVersionRequirementId(versions[0].id);
      setCompareVersionRequirementId(versions[0].id);
      return;
    }
    setBaseVersionRequirementId(versions[versions.length - 2].id);
    setCompareVersionRequirementId(versions[versions.length - 1].id);
  }, [versions]);

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

  const nodeRiskMap = useMemo(() => buildNodeRiskMap(riskItems), [riskItems]);
  const mindMapData = useMemo(() => ruleNodesToMindMapData(domainNodes, nodeRiskMap), [domainNodes, nodeRiskMap]);

  const onMindMapNodeClick = useCallback(
    (nodeId: string) => {
      const domainNode = nodeMap.get(nodeId);
      if (!domainNode) return;
      setFocusedNodeId(nodeId);
      setContextMenu(null);
    },
    [nodeMap],
  );

  const onMindMapNodeContextMenu = useCallback(
    (nodeId: string, position: { x: number; y: number }) => {
      const domainNode = nodeMap.get(nodeId);
      if (!domainNode) return;
      setFocusedNodeId(nodeId);
      setContextMenu({ x: position.x, y: position.y, nodeId });
    },
    [nodeMap],
  );

  const handleContextMenuAction = useCallback(
    (key: string) => {
      if (!contextMenu) return;
      const domainNode = nodeMap.get(contextMenu.nodeId);
      setContextMenu(null);

      if (!domainNode) return;

      switch (key) {
        case "edit":
          setEditingNode(domainNode);
          form.setFieldsValue(domainNode);
          break;
        case "addChild":
          createForm.resetFields();
          createForm.setFieldsValue({ parent_id: domainNode.id, node_type: "condition", risk_level: "medium" });
          setCreateOpen(true);
          break;
        case "delete":
          Modal.confirm({
            title: "确认删除",
            content: `确定要删除节点「${domainNode.content.length > 30 ? domainNode.content.slice(0, 30) + "..." : domainNode.content}」吗？`,
            okText: "删除",
            okButtonProps: { danger: true },
            cancelText: "取消",
            onOk: async () => {
              const resp = await deleteRuleNode(domainNode.id);
              setLastImpact(resp.impact.needs_review_case_ids);
              message.success("节点已删除");
              await reload();
            },
          });
          break;
      }
    },
    [contextMenu, createForm, form, nodeMap, reload],
  );

  useEffect(() => {
    if (!contextMenu) return;

    const dismiss = () => setContextMenu(null);
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };

    document.addEventListener("click", dismiss);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("click", dismiss);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [contextMenu]);

  const syncCanvasChanges = useCallback(
    (nextTree: MindMapTreeNode) => {
      if (!activeRequirementId || isReadonlyVersion) return;
      if (suppressCanvasSyncRef.current) return;
      const syncRequirementId = activeRequirementId;
      pendingCanvasTreeRef.current = nextTree;

      if (canvasSyncTimerRef.current) {
        window.clearTimeout(canvasSyncTimerRef.current);
      }

      canvasSyncTimerRef.current = window.setTimeout(async () => {
        canvasSyncTimerRef.current = null;
        if (isCanvasSyncingRef.current) return;
        if (suppressCanvasSyncRef.current) {
          pendingCanvasTreeRef.current = null;
          return;
        }
        if (activeRequirementIdRef.current !== syncRequirementId) {
          pendingCanvasTreeRef.current = null;
          return;
        }
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
                requirement_id: syncRequirementId,
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

          for (const removedNode of removed) {
            const resp = await deleteRuleNode(removedNode.id);
            resp.impact.needs_review_case_ids.forEach((id) => impactSet.add(id));
          }

          setLastImpact(Array.from(impactSet));
          message.success(
            `画布变更已同步（新增 ${added.length} / 更新 ${updates.length} / 删除 ${removed.length}）`,
          );
          await reload(syncRequirementId);
        } catch {
          message.error("画布变更同步失败，已刷新回服务端最新数据");
          await reload(syncRequirementId);
        } finally {
          isCanvasSyncingRef.current = false;
          if (pendingCanvasTreeRef.current && !suppressCanvasSyncRef.current) {
            syncCanvasChanges(pendingCanvasTreeRef.current);
          }
        }
      }, 420);
    },
    [activeRequirementId, isReadonlyVersion, reload],
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
    if (!activeRequirementId) {
      message.warning("请先选择需求");
      return;
    }

    const values = await createForm.validateFields();
    await createRuleNode({
      requirement_id: activeRequirementId,
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

  const handleCreateVersion = async () => {
    if (!selectedProjectId || !activeRequirementId) {
      message.warning("请先选择项目和需求");
      return;
    }

    const created = await createNewVersion(selectedProjectId, activeRequirementId);
    const updatedRequirements = await fetchRequirements(selectedProjectId);
    setRequirements(updatedRequirements);
    setSelectedRequirementId(created.id);
    switchRequirement(created.id);
    await reloadVersions(created.id);
    message.success(`已创建 v${created.version}`);
  };

  const loadDiffHistory = useCallback(async () => {
    if (!selectedProjectId) return;
    setDiffHistoryLoading(true);
    try {
      const activeReq = requirements.find((r) => r.id === activeRequirementId);
      const groupId = activeReq?.requirement_group_id ?? undefined;
      const list = await fetchDiffHistory(selectedProjectId, groupId);
      setDiffHistory(list);
    } catch {
      /* ignore */
    } finally {
      setDiffHistoryLoading(false);
    }
  }, [selectedProjectId, activeRequirementId, requirements]);

  const handleRunDiff = async () => {
    if (!baseVersionRequirementId || !compareVersionRequirementId) {
      message.warning("请选择对比版本");
      return;
    }
    if (baseVersionRequirementId === compareVersionRequirementId) {
      message.warning("基准版本和对比版本不能相同");
      return;
    }

    setDiffLoading(true);
    try {
      const result = await fetchSemanticDiff(baseVersionRequirementId, compareVersionRequirementId);
      setSemanticDiffResult(result);
      loadDiffHistory();
    } catch (error) {
      message.error(getErrorMessage(error, "版本对比失败"));
    } finally {
      setDiffLoading(false);
    }
  };

  const handleDeleteDiffRecord = async (recordId: number) => {
    try {
      await deleteDiffRecord(recordId);
      message.success("已删除");
      loadDiffHistory();
    } catch (error) {
      message.error(getErrorMessage(error, "删除失败"));
    }
  };

  const handleCreateSession = async () => {
    if (!activeRequirementId) {
      message.warning("请先选择需求");
      return;
    }
    const created = await createRuleTreeSession(activeRequirementId, "规则树会话");
    await reloadSessions(activeRequirementId);
    setSelectedSessionId(created.id);
    message.success("会话已创建");
  };

  const sessionStep = useMemo(() => {
    if (!selectedSessionId) return 0;
    if (sessionConfirmed) return 2;
    if (sessionGenerateResult || sessionUpdateResult) return 1;
    return 0;
  }, [selectedSessionId, sessionConfirmed, sessionGenerateResult, sessionUpdateResult]);

  const openSessionPanel = () => {
    if (!activeRequirementId) {
      message.warning("请先选择需求");
      return;
    }
    const requirement = requirements.find((item) => item.id === activeRequirementId);
    setSessionRequirementText(requirement?.raw_text || "");
    setSessionTitleInput(requirement?.title ? `${requirement.title} 规则树生成` : "规则树生成");
    setShowSessionUpdate(false);
    setShowSessionHistory(false);
    setSessionConfirmed(false);
    setSessionImageFile([]);
    setSessionPanelOpen(true);
  };

  const handleGenerateBySession = async () => {
    if (!selectedSessionId) {
      message.warning("请先创建并选择会话");
      return;
    }
    if (!sessionRequirementText.trim()) {
      message.warning("请输入需求文本");
      return;
    }

    setSessionLoading(true);
    try {
      const rawFile = sessionImageFile[0]?.originFileObj as File | undefined;
      const result = await generateRuleTreeSession(selectedSessionId, {
        requirement_text: sessionRequirementText.trim(),
        title: sessionTitleInput.trim() || undefined,
        image: rawFile,
      });
      setSessionGenerateResult(result);
      setSessionUpdateResult(null);
      setSessionConfirmed(false);
      const detail = await fetchRuleTreeSessionDetail(selectedSessionId);
      setSessionDetail(detail);
      message.success("规则树生成完成");
    } catch (error) {
      message.error(getErrorMessage(error, "会话生成失败"));
    } finally {
      setSessionLoading(false);
    }
  };

  const handleSessionConfirmImport = async () => {
    if (!selectedSessionId) {
      message.warning("请先选择会话");
      return;
    }
    const treeJson = sessionUpdateResult?.updated_tree || sessionGenerateResult?.reviewed_tree;
    if (!treeJson) {
      message.warning("暂无可确认导入的会话树");
      return;
    }

    setSessionConfirmLoading(true);
    try {
      const resp = await confirmRuleTreeSession(selectedSessionId, {
        tree_json: treeJson as unknown as Record<string, unknown>,
        requirement_text: sessionUpdateText.trim() || sessionRequirementText.trim(),
      });
      await reload();
      const detail = await fetchRuleTreeSessionDetail(selectedSessionId);
      setSessionDetail(detail);
      message.success(`确认导入成功，写入 ${resp.imported_nodes} 个节点`);
      setSessionConfirmed(true);
    } catch (error) {
      message.error(getErrorMessage(error, "确认导入失败"));
    } finally {
      setSessionConfirmLoading(false);
    }
  };

  const handleApplyHistorySnapshot = async (msg: { tree_snapshot: string | null }) => {
    if (!selectedSessionId || !msg.tree_snapshot) return;
    const treeJson = JSON.parse(msg.tree_snapshot);
    setSessionConfirmLoading(true);
    try {
      const resp = await confirmRuleTreeSession(selectedSessionId, {
        tree_json: treeJson,
        requirement_text: sessionUpdateText.trim() || sessionRequirementText.trim() || "",
      });
      await reload();
      const detail = await fetchRuleTreeSessionDetail(selectedSessionId);
      setSessionDetail(detail);
      message.success(`已从历史记录恢复，写入 ${resp.imported_nodes} 个节点`);
      setSessionConfirmed(true);
    } catch (error) {
      message.error(getErrorMessage(error, "从历史记录恢复失败"));
    } finally {
      setSessionConfirmLoading(false);
    }
  };

  const handleSessionIncrementalUpdate = async () => {
    if (!selectedSessionId) {
      message.warning("请先选择会话");
      return;
    }
    if (!sessionUpdateText.trim()) {
      message.warning("请输入新版需求文本");
      return;
    }

    setSessionUpdateLoading(true);
    try {
      const result = await updateRuleTreeSession(selectedSessionId, {
        new_requirement_text: sessionUpdateText.trim(),
      });
      setSessionUpdateResult(result);
      setSessionConfirmed(false);
      setShowSessionUpdate(false);
      const detail = await fetchRuleTreeSessionDetail(selectedSessionId);
      setSessionDetail(detail);
      message.success("需求更新完成");
    } catch (error) {
      message.error(getErrorMessage(error, "会话增量更新失败"));
    } finally {
      setSessionUpdateLoading(false);
    }
  };

  const handleExport = async (type: MindMapExportType) => {
    try {
      await mindMapRef.current?.exportAs(type, "规则树");
      message.success(`导出 ${type.toUpperCase()} 成功`);
    } catch {
      message.error("导出失败，请重试");
    }
  };

  const openTestPlanDrawer = async () => {
    if (!activeRequirementId) {
      message.warning("请先选择需求");
      return;
    }
    if (domainNodes.length === 0) {
      message.warning("规则树为空，请先创建规则树");
      return;
    }

    setTestPlanSessionLoading(true);
    setTestPlanDrawerOpen(true);

    try {
      const resp = await getTestPlanSessions(activeRequirementId);

      const displayable = resp.sessions.filter((s) =>
        ["plan_generated", "cases_generated", "confirmed", "archived"].includes(s.status),
      );
      setHistorySessions(displayable);

      const activeSession = resp.sessions.find(
        (s) =>
          s.status === "plan_generated" ||
          s.status === "cases_generated",
      );

      if (activeSession) {
        setCurrentSessionId(activeSession.id);
        setCurrentSessionConfirmed(false);
        setSessionCreatedAt(activeSession.updated_at || activeSession.created_at);
        setTestPlanMarkdown(activeSession.plan_markdown || "");
        setTestPlanPoints(activeSession.test_points || []);

        if (activeSession.status === "cases_generated" && activeSession.generated_cases) {
          setGeneratedCases(activeSession.generated_cases);
          setTestPlanStep(2);
        } else {
          setGeneratedCases([]);
          setTestPlanStep(1);
        }
      } else {
        setCurrentSessionId(null);
        setCurrentSessionConfirmed(false);
        setSessionCreatedAt(null);
        setTestPlanStep(0);
        setTestPlanMarkdown("");
        setTestPlanPoints([]);
        setGeneratedCases([]);
      }
    } catch {
      setCurrentSessionId(null);
      setCurrentSessionConfirmed(false);
      setSessionCreatedAt(null);
      setHistorySessions([]);
      setTestPlanStep(0);
      setTestPlanMarkdown("");
      setTestPlanPoints([]);
      setGeneratedCases([]);
    } finally {
      setTestPlanSessionLoading(false);
    }
  };

  const handleRestoreSession = (session: TestPlanSession, targetStep: number) => {
    setCurrentSessionId(session.id);
    setCurrentSessionConfirmed(session.status === "confirmed");
    setSessionCreatedAt(session.updated_at || session.created_at);
    setTestPlanMarkdown(session.plan_markdown || "");
    setTestPlanPoints(session.test_points || []);
    setGeneratedCases(session.generated_cases || []);
    setIsEditingPlan(false);
    setTestPlanStep(targetStep);
  };

  const sessionStatusConfig: Record<string, { label: string; color: string }> = {
    plan_generated: { label: "已生成方案", color: "blue" },
    cases_generated: { label: "已生成用例", color: "green" },
    confirmed: { label: "已导入", color: "default" },
    archived: { label: "已归档", color: "default" },
  };

  const handleGenerateTestPlan = async () => {
    if (!activeRequirementId) return;
    setTestPlanLoading(true);
    try {
      let sessionId = currentSessionId;
      if (!sessionId) {
        const session = await createTestPlanSession(activeRequirementId);
        sessionId = session.id;
        setCurrentSessionId(sessionId);
        setCurrentSessionConfirmed(false);
      }

      const result = await generateTestPlan(activeRequirementId, sessionId);
      setTestPlanMarkdown(result.markdown);
      setTestPlanPoints(result.test_points);
      setSessionCreatedAt(new Date().toISOString());
      setTestPlanStep(1);
      message.success("测试方案生成完成");
    } catch (error) {
      message.error(getErrorMessage(error, "生成测试方案失败"));
    } finally {
      setTestPlanLoading(false);
    }
  };

  const handleGenerateTestCases = async () => {
    if (!activeRequirementId) return;
    setTestCaseGenLoading(true);
    try {
      const result = await generateTestCases({
        requirement_id: activeRequirementId,
        test_plan_markdown: testPlanMarkdown,
        test_points: testPlanPoints,
        session_id: currentSessionId,
      });
      setGeneratedCases(result.test_cases);
      setSessionCreatedAt(new Date().toISOString());
      setTestPlanStep(2);
      message.success(`已生成 ${result.test_cases.length} 条测试用例`);
    } catch (error) {
      message.error(getErrorMessage(error, "生成测试用例失败"));
    } finally {
      setTestCaseGenLoading(false);
    }
  };

  const handleConfirmTestCases = async () => {
    if (!activeRequirementId || generatedCases.length === 0) return;
    setTestCaseConfirmLoading(true);
    try {
      const result = await confirmTestCases({
        requirement_id: activeRequirementId,
        test_cases: generatedCases,
        session_id: currentSessionId,
      });
      message.success(`成功导入 ${result.created_count} 条测试用例`);
      setCurrentSessionId(null);
      setCurrentSessionConfirmed(false);
      setSessionCreatedAt(null);
      setTestPlanDrawerOpen(false);
    } catch (error) {
      message.error(getErrorMessage(error, "导入测试用例失败"));
    } finally {
      setTestCaseConfirmLoading(false);
    }
  };

  const handleRemoveGeneratedCase = (index: number) => {
    setGeneratedCases((prev) => {
      const updated = prev.filter((_, i) => i !== index);
      if (currentSessionId && !currentSessionConfirmed) {
        updateSessionCases(currentSessionId, updated).catch(() => {});
      }
      return updated;
    });
  };

  const handleStartEditPlan = () => {
    setEditingMarkdown(testPlanMarkdown);
    setEditingPoints(testPlanPoints.map((p) => ({ ...p })));
    setIsEditingPlan(true);
  };

  const handleCancelEditPlan = () => {
    setIsEditingPlan(false);
    setEditingMarkdown("");
    setEditingPoints([]);
  };

  const handleSavePlan = () => {
    Modal.confirm({
      title: "确认保存修改",
      content: "保存后将覆盖 AI 生成的原始方案，历史记录中将显示您修改后的版本。确定要保存吗？",
      okText: "确认保存",
      cancelText: "取消",
      onOk: async () => {
        if (!currentSessionId) {
          message.warning("当前没有关联的会话，无法保存");
          return;
        }
        setPlanSaveLoading(true);
        try {
          await updateTestPlan(currentSessionId, {
            plan_markdown: editingMarkdown,
            test_points: editingPoints,
          });
          setTestPlanMarkdown(editingMarkdown);
          setTestPlanPoints(editingPoints);
          setIsEditingPlan(false);
          setGeneratedCases([]);
          message.success("测试方案已更新");
        } catch (error) {
          message.error(getErrorMessage(error, "保存测试方案失败"));
        } finally {
          setPlanSaveLoading(false);
        }
      },
    });
  };

  const handleEditPoint = (index: number) => {
    const point = editingPoints[index];
    editingPointForm.setFieldsValue(point);
    setEditingPointIndex(index);
    setEditingPointModalOpen(true);
  };

  const handleSavePoint = async () => {
    const values = await editingPointForm.validateFields();
    setEditingPoints((prev) => {
      const next = [...prev];
      if (editingPointIndex !== null && editingPointIndex < next.length) {
        next[editingPointIndex] = { ...next[editingPointIndex], ...values };
      }
      return next;
    });
    setEditingPointModalOpen(false);
    setEditingPointIndex(null);
  };

  const handleDeletePoint = (index: number) => {
    setEditingPoints((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAddPoint = () => {
    const newId = `tp_custom_${Date.now()}`;
    editingPointForm.resetFields();
    editingPointForm.setFieldsValue({
      id: newId,
      name: "",
      description: "",
      type: "normal",
      priority: "medium",
      related_node_ids: [],
    });
    setEditingPointIndex(null);
    setEditingPointModalOpen(true);
  };

  const handleSaveNewPoint = async () => {
    const values = await editingPointForm.validateFields();
    if (editingPointIndex !== null) {
      handleSavePoint();
      return;
    }
    const newPoint: TestPoint = {
      id: values.id || `tp_custom_${Date.now()}`,
      name: values.name,
      description: values.description,
      type: values.type,
      priority: values.priority,
      related_node_ids: values.related_node_ids || [],
    };
    setEditingPoints((prev) => [...prev, newPoint]);
    setEditingPointModalOpen(false);
  };

  const testPlanCoverageStats = useMemo(() => {
    const coverableNodes = domainNodes.filter(
      (n) => n.node_type === "action" || n.node_type === "branch" || n.node_type === "exception",
    );
    const coveredIds = new Set(generatedCases.flatMap((c) => c.related_node_ids));
    const coveredCount = coverableNodes.filter((n) => coveredIds.has(n.id)).length;
    return { total: coverableNodes.length, covered: coveredCount };
  }, [domainNodes, generatedCases]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 150px)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <Space size={6}>
          <Select
            style={{ width: 280 }}
            value={activeRequirementId ?? undefined}
            placeholder="请选择版本"
            loading={versionLoading}
            options={versions.map((item) => ({
              value: item.id,
              label: `v${item.version}${item.id === latestVersionRequirementId ? " (最新)" : ""} · ${item.title}`,
            }))}
            onChange={(value) => switchRequirement(value)}
          />
          <Button onClick={handleCreateVersion} disabled={!selectedProjectId || !activeRequirementId}>
            创建新版本
          </Button>
          <Button onClick={() => setDiffOpen(true)} disabled={versions.length < 2}>
            版本对比
          </Button>
        </Space>

        <Divider type="vertical" style={{ height: 24, margin: "0 4px" }} />

        {!isReadonlyVersion ? (
          <Button type="primary" onClick={() => setCreateOpen(true)}>
            新增节点
          </Button>
        ) : (
          <Tag color="gold" style={{ margin: 0 }}>当前版本只读</Tag>
        )}

        <Divider type="vertical" style={{ height: 24, margin: "0 4px" }} />

        <Button
          icon={<RobotOutlined />}
          onClick={openSessionPanel}
          disabled={!activeRequirementId}
        >
          AI 生成规则树
        </Button>

        <Button
          icon={<ExperimentOutlined />}
          onClick={openTestPlanDrawer}
          disabled={!activeRequirementId || domainNodes.length === 0}
        >
          AI 生成测试方案
        </Button>

        <Divider type="vertical" style={{ height: 24, margin: "0 4px" }} />

        <Space size={6}>
          <Button onClick={() => mindMapRef.current?.fitView()}>适应画布</Button>
          <Dropdown
            menu={{
              items: [
                { key: "png", label: "导出 PNG" },
                { key: "svg", label: "导出 SVG" },
                { key: "xmind", label: "导出 XMind" },
              ],
              onClick: ({ key }) => handleExport(key as MindMapExportType),
            }}
          >
            <Button>
              导出 <DownOutlined />
            </Button>
          </Dropdown>
          <Space size={4}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>文本宽度</Typography.Text>
            <InputNumber
              min={80}
              max={800}
              step={10}
              size="small"
              value={textAutoWrapWidth}
              onChange={(value) => setTextAutoWrapWidth(typeof value === "number" ? value : 150)}
              style={{ width: 80 }}
            />
          </Space>
          <Button
            icon={<WarningOutlined />}
            type={riskPanelVisible ? "primary" : "default"}
            onClick={() => setRiskPanelVisible((v) => !v)}
          >
            风险识别{riskItems.filter((r) => r.decision === "pending").length > 0
              ? ` (${riskItems.filter((r) => r.decision === "pending").length})`
              : ""}
          </Button>
        </Space>
      </div>

      {lastImpact.length > 0 && (
        <Alert
          style={{ marginBottom: 12 }}
          type="warning"
          message={`变更影响: ${lastImpact.length} 条用例已标记为待复核 (${lastImpact.join(", ")})`}
        />
      )}

      {sessionGenerateResult && (
        <Alert
          style={{ marginBottom: 12 }}
          type="success"
          message={`AI 生成结果：新增 ${sessionGenerateResult.diff.summary.added} / 修改 ${sessionGenerateResult.diff.summary.modified} / 删除 ${sessionGenerateResult.diff.summary.deleted}`}
        />
      )}

      {sessionUpdateResult && (
        <Alert
          style={{ marginBottom: 12 }}
          type="info"
          message={`需求更新结果：新增 ${sessionUpdateResult.node_diff.summary.added} / 修改 ${sessionUpdateResult.node_diff.summary.modified} / 删除 ${sessionUpdateResult.node_diff.summary.deleted}`}
          description={sessionUpdateResult.requirement_diff || "未检测到需求文本差异"}
        />
      )}

      {!activeRequirementId ? (
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
            <div style={{ padding: 10, borderBottom: "1px solid #eef2f7", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Typography.Text>
                当前选中：{focusedNodeId ? nodeMap.get(focusedNodeId)?.content || focusedNodeId : "-"}
              </Typography.Text>
              {!isReadonlyVersion && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>右键节点可编辑</Typography.Text>
              )}
            </div>
            <div style={{ flex: 1, position: "relative" }}>
              <MindMapWrapper
                key={activeRequirementId ?? "no-requirement"}
                ref={mindMapRef}
                data={mindMapData}
                selectedNodeId={focusedNodeId}
                layout={layout}
                theme={theme}
                editable={!isReadonlyVersion}
                textAutoWrapWidth={textAutoWrapWidth}
                onNodeClick={onMindMapNodeClick}
                onNodeContextMenu={isReadonlyVersion ? undefined : onMindMapNodeContextMenu}
                onDataChange={syncCanvasChanges}
              />
            </div>
          </div>

          {riskPanelVisible && (
            <div
              style={{
                width: 340,
                minHeight: 0,
                border: "1px solid #d7e2ee",
                borderRadius: 10,
                display: "flex",
                flexDirection: "column",
                overflow: "hidden",
              }}
            >
              <RiskPanel
                requirementId={activeRequirementId}
                onNodeLocate={(nodeId) => {
                  setFocusedNodeId(nodeId);
                  mindMapRef.current?.focusNode(nodeId);
                  mindMapRef.current?.highlightNode(nodeId);
                }}
                onRiskConverted={() => {
                  reload();
                }}
                onRisksChange={(risks) => setRiskItems(risks)}
              />
            </div>
          )}
        </div>
      )}

      {contextMenu && (
        <div
          style={{
            position: "fixed",
            left: contextMenu.x,
            top: contextMenu.y,
            zIndex: 1050,
            boxShadow: "0 3px 12px rgba(0,0,0,0.15)",
            borderRadius: 8,
            background: "#fff",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <Menu
            style={{ borderRadius: 8, minWidth: 160 }}
            items={[
              { key: "edit", label: "编辑节点", icon: <EditOutlined /> },
              { key: "addChild", label: "新增子节点", icon: <PlusOutlined /> },
              { type: "divider" },
              { key: "delete", label: "删除节点", icon: <DeleteOutlined />, danger: true },
            ]}
            onClick={({ key }) => handleContextMenuAction(key)}
          />
        </div>
      )}

      <Drawer
        open={!!editingNode || createOpen}
        title={editingNode ? "编辑规则节点" : "新增规则节点"}
        onClose={() => {
          setEditingNode(null);
          setCreateOpen(false);
        }}
        width={420}
      >
        {editingNode ? (
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
        ) : (
          <Form layout="vertical" form={createForm}>
            <Form.Item name="content" label="节点内容" rules={[{ required: true, message: "请输入内容" }]}>
              <Input.TextArea rows={3} />
            </Form.Item>
            <Form.Item name="node_type" label="节点类型" initialValue="condition" rules={[{ required: true }]}>
              <Select options={nodeTypeOptions} />
            </Form.Item>
            <Form.Item name="risk_level" label="风险等级" initialValue="medium" rules={[{ required: true }]}>
              <Select options={riskOptions} />
            </Form.Item>
            <Form.Item name="parent_id" label="父节点 (可选)">
              <Select allowClear options={domainNodes.map((node) => ({ value: node.id, label: node.content }))} />
            </Form.Item>
            <Button type="primary" onClick={handleCreateNode}>
              创建节点
            </Button>
          </Form>
        )}
      </Drawer>

      <Drawer
        open={sessionPanelOpen}
        title="AI 规则树生成"
        width={640}
        onClose={() => {
          setSessionPanelOpen(false);
          setShowSessionUpdate(false);
          setShowSessionHistory(false);
        }}
      >
        <div style={{ marginBottom: 20 }}>
          <Typography.Text strong style={{ display: "block", marginBottom: 8 }}>选择会话</Typography.Text>
          <div style={{ display: "flex", gap: 8 }}>
            <Select
              style={{ flex: 1 }}
              value={selectedSessionId}
              placeholder="选择或新建会话"
              options={sessions.map((item) => ({
                value: item.id,
                label: `${item.title} (${item.status})`,
              }))}
              onChange={(value) => setSelectedSessionId(value)}
            />
            <Button onClick={handleCreateSession} disabled={!activeRequirementId}>
              新建
            </Button>
          </div>
        </div>

        <Steps
          current={sessionStep}
          size="small"
          style={{ marginBottom: 24 }}
          items={[
            { title: "输入需求" },
            { title: "查看结果" },
            { title: "应用到规则树" },
          ]}
        />

        <div style={{ marginBottom: 20 }}>
          <Form layout="vertical">
            <Form.Item label="会话标题">
              <Input value={sessionTitleInput} onChange={(event) => setSessionTitleInput(event.target.value)} />
            </Form.Item>
            <Form.Item label="需求文本" style={{ marginBottom: 12 }}>
              <Input.TextArea
                rows={6}
                value={sessionRequirementText}
                onChange={(event) => setSessionRequirementText(event.target.value)}
                placeholder="请输入用于生成规则树的需求文本"
              />
            </Form.Item>
            <Form.Item label="流程图（可选，支持图片识别）" style={{ marginBottom: 12 }}>
              <Upload.Dragger
                accept="image/*"
                maxCount={1}
                fileList={sessionImageFile}
                beforeUpload={() => false}
                onChange={({ fileList }) => setSessionImageFile(fileList.slice(-1))}
              >
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p className="ant-upload-text">点击或拖拽上传流程图</p>
                <p className="ant-upload-hint">上传后 AI 将结合图片内容辅助生成规则树</p>
              </Upload.Dragger>
            </Form.Item>
          </Form>
          <Button
            type="primary"
            onClick={handleGenerateBySession}
            loading={sessionLoading}
            disabled={!selectedSessionId || !sessionRequirementText.trim()}
          >
            开始生成
          </Button>
        </div>

        {sessionGenerateResult && (
          <Alert
            type="success"
            message={`生成完成：新增 ${sessionGenerateResult.diff.summary.added} / 修改 ${sessionGenerateResult.diff.summary.modified} / 删除 ${sessionGenerateResult.diff.summary.deleted}`}
            style={{ marginBottom: 12 }}
          />
        )}

        {sessionUpdateResult && (
          <Alert
            type="info"
            message={`更新完成：新增 ${sessionUpdateResult.node_diff.summary.added} / 修改 ${sessionUpdateResult.node_diff.summary.modified} / 删除 ${sessionUpdateResult.node_diff.summary.deleted}`}
            description={sessionUpdateResult.requirement_diff || "未检测到需求文本差异"}
            style={{ marginBottom: 12 }}
          />
        )}

        {(sessionGenerateResult || sessionUpdateResult) && (
          <div style={{ marginBottom: 20 }}>
            <Space>
              <Button
                onClick={() => {
                  if (!showSessionUpdate) {
                    const requirement = requirements.find((item) => item.id === activeRequirementId);
                    setSessionUpdateText(requirement?.raw_text || "");
                  }
                  setShowSessionUpdate(!showSessionUpdate);
                }}
              >
                {showSessionUpdate ? "收起" : "修改需求文本"}
              </Button>
              <Button type="primary" onClick={handleSessionConfirmImport} loading={sessionConfirmLoading} disabled={sessionConfirmed}>
                应用到规则树
              </Button>
            </Space>
          </div>
        )}

        {showSessionUpdate && (
          <div style={{ marginBottom: 20, padding: 16, background: "#fafbfc", borderRadius: 8 }}>
            <Typography.Text strong style={{ display: "block", marginBottom: 8 }}>修改后的需求文本</Typography.Text>
            <Input.TextArea
              rows={6}
              value={sessionUpdateText}
              onChange={(event) => setSessionUpdateText(event.target.value)}
              placeholder="请输入修改后的需求文本"
            />
            <Button
              type="primary"
              style={{ marginTop: 12 }}
              onClick={handleSessionIncrementalUpdate}
              loading={sessionUpdateLoading}
              disabled={!sessionUpdateText.trim()}
            >
              提交更新
            </Button>
          </div>
        )}

        <Divider style={{ marginTop: 8, marginBottom: 12 }} />

        <Button
          type="text"
          icon={<HistoryOutlined />}
          onClick={() => setShowSessionHistory(!showSessionHistory)}
          style={{ marginBottom: 12, padding: 0 }}
        >
          {showSessionHistory ? "收起历史记录" : "查看历史记录"}
        </Button>

        {showSessionHistory && (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {(sessionDetail?.messages || []).length === 0 ? (
              <Typography.Text type="secondary">暂无历史消息</Typography.Text>
            ) : (
              (sessionDetail?.messages || []).map((item) => (
                <div
                  key={item.id}
                  style={{
                    border: "1px solid #eef2f7",
                    borderRadius: 8,
                    padding: 10,
                    background: item.role === "assistant" ? "#f7fbff" : "#fff",
                  }}
                >
                  <Space style={{ marginBottom: 6 }}>
                    <Tag>{item.role}</Tag>
                    <Tag color="blue">{item.message_type}</Tag>
                    <Typography.Text type="secondary">{new Date(item.created_at).toLocaleString()}</Typography.Text>
                  </Space>
                  <Typography.Paragraph style={{ marginBottom: item.role === "assistant" && item.tree_snapshot ? 8 : 0, whiteSpace: "pre-wrap" }}>
                    {item.content.length > 500 ? `${item.content.slice(0, 500)}...` : item.content}
                  </Typography.Paragraph>
                  {item.role === "assistant" && item.tree_snapshot && (
                    <div style={{ textAlign: "right" }}>
                      <Popconfirm
                        title="确定要将此版本应用到规则树吗？当前规则树将被覆盖。"
                        onConfirm={() => handleApplyHistorySnapshot(item)}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button size="small" type="primary" ghost loading={sessionConfirmLoading}>
                          应用此版本到规则树
                        </Button>
                      </Popconfirm>
                    </div>
                  )}
                </div>
              ))
            )}
          </Space>
        )}
      </Drawer>

      <Drawer
        open={testPlanDrawerOpen}
        title="AI 生成测试方案"
        width={720}
        onClose={() => {
          setTestPlanDrawerOpen(false);
          setIsEditingPlan(false);
        }}
      >
        <Spin spinning={testPlanSessionLoading} tip="加载会话...">
        <Steps
          current={testPlanStep}
          size="small"
          style={{ marginBottom: 24 }}
          items={[
            { title: "生成测试方案" },
            { title: "审核测试方案" },
            { title: "生成并导入用例" },
          ]}
        />

        {testPlanStep === 0 && (
          <div>
            <Alert
              type="info"
              style={{ marginBottom: 16 }}
              message="基于当前规则树生成测试方案"
              description={
                <Space direction="vertical" size={4}>
                  <span>总节点数：{domainNodes.length}</span>
                  <span>
                    可测试节点：
                    {domainNodes.filter((n) => n.node_type === "action" || n.node_type === "branch" || n.node_type === "exception").length}
                    （action / branch / exception）
                  </span>
                </Space>
              }
            />
            <Button
              type="primary"
              size="large"
              icon={<ExperimentOutlined />}
              onClick={handleGenerateTestPlan}
              loading={testPlanLoading}
              block
            >
              开始生成测试方案
            </Button>

            {historySessions.length > 0 && (
              <>
                <Divider style={{ margin: "20px 0 12px" }}>
                  <Space size={4}>
                    <HistoryOutlined />
                    <span>历史记录</span>
                  </Space>
                </Divider>
                <List
                  size="small"
                  dataSource={historySessions}
                  renderItem={(s) => {
                    const cfg = sessionStatusConfig[s.status] || { label: s.status, color: "default" };
                    const caseCount = s.generated_cases?.length ?? 0;
                    const hasCase = caseCount > 0;
                    const isConfirmed = s.status === "confirmed";
                    return (
                      <List.Item
                        style={{ padding: "10px 12px" }}
                        actions={[
                          <Button
                            key="view"
                            size="small"
                            type="link"
                            disabled={!s.plan_markdown}
                            onClick={() => handleRestoreSession(s, 1)}
                          >
                            查看方案
                          </Button>,
                          ...(hasCase
                            ? [
                                <Button
                                  key="import"
                                  size="small"
                                  type="link"
                                  onClick={() => handleRestoreSession(s, 2)}
                                >
                                  {isConfirmed ? "重新导入" : "导入用例"}
                                </Button>,
                              ]
                            : []),
                        ]}
                      >
                        <List.Item.Meta
                          title={
                            <Space size={8}>
                              <Typography.Text style={{ fontSize: 13 }}>
                                {new Date(s.created_at).toLocaleString()}
                              </Typography.Text>
                              <Tag color={cfg.color}>{cfg.label}</Tag>
                              {hasCase && (
                                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                  {caseCount} 条用例
                                </Typography.Text>
                              )}
                            </Space>
                          }
                          description={
                            s.test_points && s.test_points.length > 0
                              ? <Typography.Text type="secondary" style={{ fontSize: 12 }}>{s.test_points.length} 个测试点</Typography.Text>
                              : null
                          }
                        />
                      </List.Item>
                    );
                  }}
                />
              </>
            )}
          </div>
        )}

        {testPlanStep === 1 && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <Typography.Title level={5} style={{ marginBottom: 0 }}>测试方案预览</Typography.Title>
              {!isEditingPlan ? (
                <Button icon={<EditOutlined />} size="small" onClick={handleStartEditPlan}>
                  编辑方案
                </Button>
              ) : (
                <Space size={8}>
                  <Tag color="orange">编辑模式</Tag>
                  <Button size="small" icon={<CloseOutlined />} onClick={handleCancelEditPlan}>
                    取消
                  </Button>
                  <Button size="small" type="primary" icon={<SaveOutlined />} onClick={handleSavePlan} loading={planSaveLoading}>
                    保存修改
                  </Button>
                </Space>
              )}
            </div>

            {isEditingPlan ? (
              <Input.TextArea
                value={editingMarkdown}
                onChange={(e) => setEditingMarkdown(e.target.value)}
                autoSize={{ minRows: 6, maxRows: 20 }}
                style={{
                  marginBottom: 16,
                  fontSize: 13,
                  lineHeight: 1.8,
                  fontFamily: "inherit",
                }}
              />
            ) : (
              <div
                style={{
                  background: "#fafbfc",
                  border: "1px solid #eef2f7",
                  borderRadius: 8,
                  padding: 16,
                  marginBottom: 16,
                  maxHeight: 400,
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.8,
                  fontSize: 13,
                }}
              >
                {testPlanMarkdown || "暂无内容"}
              </div>
            )}

            {(() => {
              const pointsData = isEditingPlan ? editingPoints : testPlanPoints;
              if (pointsData.length === 0 && !isEditingPlan) return null;
              return (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <Typography.Title level={5} style={{ marginBottom: 0 }}>
                      测试点列表（{pointsData.length} 个）
                    </Typography.Title>
                    {isEditingPlan && (
                      <Button size="small" icon={<PlusOutlined />} onClick={handleAddPoint}>
                        添加测试点
                      </Button>
                    )}
                  </div>
                  <Table
                    size="small"
                    rowKey="id"
                    dataSource={pointsData}
                    pagination={false}
                    style={{ marginBottom: 16 }}
                    columns={[
                      { title: "测试点", dataIndex: "name", width: 160 },
                      { title: "描述", dataIndex: "description", ellipsis: true },
                      {
                        title: "类型",
                        dataIndex: "type",
                        width: 80,
                        render: (type: string) => {
                          const colors: Record<string, string> = { normal: "blue", exception: "red", boundary: "orange" };
                          return <Tag color={colors[type] || "default"}>{type}</Tag>;
                        },
                      },
                      {
                        title: "优先级",
                        dataIndex: "priority",
                        width: 80,
                        render: (p: string) => {
                          const colors: Record<string, string> = { high: "red", medium: "orange", low: "blue" };
                          return <Tag color={colors[p] || "default"}>{p}</Tag>;
                        },
                      },
                      {
                        title: "关联节点",
                        dataIndex: "related_node_ids",
                        width: 80,
                        render: (ids: string[]) => ids?.length || 0,
                      },
                      ...(isEditingPlan
                        ? [
                            {
                              title: "操作",
                              width: 100,
                              render: (_: unknown, __: unknown, index: number) => (
                                <Space size={4}>
                                  <Button size="small" type="link" onClick={() => handleEditPoint(index)}>
                                    编辑
                                  </Button>
                                  <Popconfirm title="确认删除该测试点？" onConfirm={() => handleDeletePoint(index)} okText="确定" cancelText="取消">
                                    <Button size="small" type="link" danger>
                                      删除
                                    </Button>
                                  </Popconfirm>
                                </Space>
                              ),
                            },
                          ]
                        : []),
                    ]}
                  />
                </>
              );
            })()}

            {sessionCreatedAt && (
              <Typography.Text type="secondary" style={{ fontSize: 12, marginBottom: 12, display: "block" }}>
                生成时间：{new Date(sessionCreatedAt).toLocaleString()}
              </Typography.Text>
            )}

            <Space>
              {currentSessionConfirmed ? (
                <Button
                  onClick={() => {
                    setCurrentSessionId(null);
                    setCurrentSessionConfirmed(false);
                    setSessionCreatedAt(null);
                    setTestPlanStep(0);
                    setTestPlanMarkdown("");
                    setTestPlanPoints([]);
                    setGeneratedCases([]);
                  }}
                >
                  返回历史记录
                </Button>
              ) : (
                <>
                  <Button
                    disabled={isEditingPlan}
                    onClick={async () => {
                      if (currentSessionId) {
                        try {
                          await archiveTestPlanSession(currentSessionId);
                        } catch { /* ignore */ }
                      }
                      setCurrentSessionId(null);
                      setCurrentSessionConfirmed(false);
                      setSessionCreatedAt(null);
                      setTestPlanStep(0);
                      setTestPlanMarkdown("");
                      setTestPlanPoints([]);
                      setGeneratedCases([]);
                    }}
                  >
                    重新生成
                  </Button>
                  <Button
                    type="primary"
                    icon={<CheckCircleOutlined />}
                    onClick={handleGenerateTestCases}
                    loading={testCaseGenLoading}
                    disabled={isEditingPlan}
                  >
                    测试方案通过，生成用例
                  </Button>
                </>
              )}
            </Space>
          </div>
        )}

        {testPlanStep === 2 && (
          <div>
            {currentSessionConfirmed && (
              <Alert
                type="warning"
                style={{ marginBottom: 12 }}
                message="该批次用例曾已导入，您可选择需要的用例重新导入"
                description="移除不需要的用例后点击下方导入按钮，移除操作不会影响历史记录中保存的原始用例数据。"
                showIcon
              />
            )}
            <Alert
              type="success"
              style={{ marginBottom: 16 }}
              message={`${currentSessionConfirmed ? "历史生成" : "已生成"} ${generatedCases.length} 条测试用例`}
              description={
                <span>
                  节点覆盖：{testPlanCoverageStats.covered} / {testPlanCoverageStats.total} 个可测试节点
                  {testPlanCoverageStats.total > 0 && (
                    <>（{Math.round((testPlanCoverageStats.covered / testPlanCoverageStats.total) * 100)}%）</>
                  )}
                </span>
              }
            />

            <Table
              size="small"
              rowKey={(_, index) => String(index)}
              dataSource={generatedCases}
              pagination={generatedCases.length > 8 ? { pageSize: 8 } : false}
              style={{ marginBottom: 16 }}
              columns={[
                { title: "标题", dataIndex: "title", width: 160, ellipsis: true },
                {
                  title: "前置条件",
                  dataIndex: "preconditions",
                  width: 180,
                  ellipsis: true,
                  render: (val: string[] | string | undefined) => {
                    if (!val) return "-";
                    if (typeof val === "string") return val;
                    return val.map((s, i) => <div key={i}>- {s}</div>);
                  },
                },
                {
                  title: "执行步骤",
                  dataIndex: "steps",
                  ellipsis: true,
                  render: (val: string[] | string | undefined) => {
                    if (!val) return "-";
                    if (typeof val === "string") return val;
                    return val.map((s, i) => <div key={i}>{i + 1}. {s}</div>);
                  },
                },
                {
                  title: "预期结果",
                  dataIndex: "expected_result",
                  width: 180,
                  ellipsis: true,
                  render: (val: string[] | string | undefined) => {
                    if (!val) return "-";
                    if (typeof val === "string") return val;
                    return val.map((s, i) => <div key={i}>- {s}</div>);
                  },
                },
                {
                  title: "风险",
                  dataIndex: "risk_level",
                  width: 70,
                  render: (level: string) => {
                    const colors: Record<string, string> = { critical: "red", high: "orange", medium: "blue", low: "green" };
                    return <Tag color={colors[level] || "default"}>{level}</Tag>;
                  },
                },
                {
                  title: "绑定节点",
                  dataIndex: "related_node_ids",
                  width: 100,
                  render: (ids: string[]) => (
                    <Tooltip
                      title={ids?.map((id) => nodeMap.get(id)?.content || id).join("、") || "无"}
                    >
                      <Tag>{ids?.length || 0} 个节点</Tag>
                    </Tooltip>
                  ),
                },
                {
                  title: "操作",
                  width: 60,
                  render: (_: unknown, __: unknown, index: number) => (
                    <Popconfirm title="确认移除？" onConfirm={() => handleRemoveGeneratedCase(index)} okText="确定" cancelText="取消">
                      <Button size="small" type="link" danger>
                        移除
                      </Button>
                    </Popconfirm>
                  ),
                },
              ]}
            />

            {sessionCreatedAt && (
              <Typography.Text type="secondary" style={{ fontSize: 12, marginBottom: 12, display: "block" }}>
                生成时间：{new Date(sessionCreatedAt).toLocaleString()}
              </Typography.Text>
            )}

            <Space>
              <Button
                onClick={() => {
                  setTestPlanStep(currentSessionConfirmed ? 0 : 1);
                }}
              >
                {currentSessionConfirmed ? "返回历史记录" : "返回测试方案"}
              </Button>
              <Button
                type="primary"
                onClick={handleConfirmTestCases}
                loading={testCaseConfirmLoading}
                disabled={generatedCases.length === 0}
              >
                {currentSessionConfirmed ? "重新导入" : "确认导入"} {generatedCases.length} 条用例
              </Button>
            </Space>
          </div>
        )}
        </Spin>

        <Modal
          title={editingPointIndex !== null ? "编辑测试点" : "添加测试点"}
          open={editingPointModalOpen}
          onCancel={() => {
            setEditingPointModalOpen(false);
            setEditingPointIndex(null);
          }}
          onOk={editingPointIndex !== null ? handleSavePoint : handleSaveNewPoint}
          okText="确定"
          cancelText="取消"
        >
          <Form layout="vertical" form={editingPointForm}>
            <Form.Item name="name" label="测试点名称" rules={[{ required: true, message: "请输入测试点名称" }]}>
              <Input />
            </Form.Item>
            <Form.Item name="description" label="描述" rules={[{ required: true, message: "请输入描述" }]}>
              <Input.TextArea rows={3} />
            </Form.Item>
            <Form.Item name="type" label="类型" rules={[{ required: true }]}>
              <Select
                options={[
                  { label: "normal", value: "normal" },
                  { label: "exception", value: "exception" },
                  { label: "boundary", value: "boundary" },
                ]}
              />
            </Form.Item>
            <Form.Item name="priority" label="优先级" rules={[{ required: true }]}>
              <Select
                options={[
                  { label: "high", value: "high" },
                  { label: "medium", value: "medium" },
                  { label: "low", value: "low" },
                ]}
              />
            </Form.Item>
          </Form>
        </Modal>
      </Drawer>

      <Modal
        title="版本对比"
        open={diffOpen}
        onCancel={() => {
          setDiffOpen(false);
          setSemanticDiffResult(null);
          setViewingHistoryResult(null);
          setDiffActiveTab("new");
        }}
        footer={null}
        width={980}
        afterOpenChange={(open) => {
          if (open) loadDiffHistory();
        }}
      >
        <Tabs
          activeKey={diffActiveTab}
          onChange={(key) => {
            setDiffActiveTab(key);
            setViewingHistoryResult(null);
          }}
          items={[
            {
              key: "new",
              label: "新对比",
              children: (
                <>
                  <Space style={{ marginBottom: 16 }} wrap>
                    <Select
                      style={{ width: 320 }}
                      placeholder="基准版本"
                      value={baseVersionRequirementId}
                      options={versions.map((item) => ({ value: item.id, label: `v${item.version} · ${item.title}` }))}
                      onChange={(value) => setBaseVersionRequirementId(value)}
                    />
                    <Select
                      style={{ width: 320 }}
                      placeholder="对比版本"
                      value={compareVersionRequirementId}
                      options={versions.map((item) => ({ value: item.id, label: `v${item.version} · ${item.title}` }))}
                      onChange={(value) => setCompareVersionRequirementId(value)}
                    />
                    <Button type="primary" onClick={handleRunDiff} loading={diffLoading}>
                      开始对比
                    </Button>
                  </Space>

                  {semanticDiffResult && (
                    <DiffResultDisplay result={semanticDiffResult} />
                  )}
                </>
              ),
            },
            {
              key: "history",
              label: `历史记录${diffHistory.length ? ` (${diffHistory.length})` : ""}`,
              children: viewingHistoryResult ? (
                <>
                  <Button
                    style={{ marginBottom: 12 }}
                    onClick={() => setViewingHistoryResult(null)}
                  >
                    返回列表
                  </Button>
                  <DiffResultDisplay result={viewingHistoryResult} />
                </>
              ) : (
                <Table
                  size="small"
                  rowKey="id"
                  loading={diffHistoryLoading}
                  dataSource={diffHistory}
                  pagination={diffHistory.length > 10 ? { pageSize: 10 } : false}
                  columns={[
                    {
                      title: "对比版本",
                      key: "versions",
                      width: 160,
                      render: (_: unknown, record: DiffRecordRead) => (
                        <span>v{record.base_version} → v{record.compare_version}</span>
                      ),
                    },
                    {
                      title: "对比方式",
                      dataIndex: "diff_type",
                      width: 100,
                      render: (t: string) => (
                        <Tag color={t === "semantic" ? "blue" : "default"}>
                          {t === "semantic" ? "语义" : "算法"}
                        </Tag>
                      ),
                    },
                    {
                      title: "变更数",
                      key: "changes",
                      width: 80,
                      render: (_: unknown, record: DiffRecordRead) =>
                        record.result.flow_changes.length,
                    },
                    {
                      title: "对比时间",
                      dataIndex: "created_at",
                      width: 180,
                      render: (v: string) => new Date(v).toLocaleString(),
                    },
                    {
                      title: "操作",
                      key: "action",
                      width: 120,
                      render: (_: unknown, record: DiffRecordRead) => (
                        <Space>
                          <Tooltip title="查看详情">
                            <Button
                              size="small"
                              type="link"
                              onClick={() => setViewingHistoryResult(record.result)}
                            >
                              查看
                            </Button>
                          </Tooltip>
                          <Popconfirm
                            title="确定删除此对比记录？"
                            onConfirm={() => handleDeleteDiffRecord(record.id)}
                            okText="确定"
                            cancelText="取消"
                          >
                            <Button size="small" type="link" danger>
                              删除
                            </Button>
                          </Popconfirm>
                        </Space>
                      ),
                    },
                  ]}
                />
              ),
            },
          ]}
        />
      </Modal>
    </div>
  );
}
