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
  Modal,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Tree,
  Typography,
  message,
} from "antd";
import { DownOutlined, HistoryOutlined, RobotOutlined, WarningOutlined } from "@ant-design/icons";
import { getErrorMessage } from "../../api/client";
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
import { aiParse, createRuleNode, deleteRuleNode, fetchRuleTree, updateRuleNode } from "../../api/rules";
import { fetchSemanticDiff } from "../../api/treeDiff";
import { useAppStore } from "../../stores/appStore";
import type {
  AIParseNode,
  AIParseResult,
  RuleTreeSession,
  RuleTreeSessionDetail,
  RuleTreeSessionGenerateResult,
  RuleTreeSessionUpdateResult,
  RequirementVersion,
  RiskItem,
  RiskLevel,
  RuleNode,
  SemanticDiffResult,
} from "../../types";
import { getNodeTypeLabel, riskLevelLabels } from "../../utils/enumLabels";
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

  const [lastImpact, setLastImpact] = useState<number[]>([]);
  const [riskItems, setRiskItems] = useState<RiskItem[]>([]);
  const [riskPanelVisible, setRiskPanelVisible] = useState(false);

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

  const loadRisks = useCallback(async (requirementId: number | null) => {
    if (!requirementId) {
      setRiskItems([]);
      return;
    }
    try {
      const resp = await fetchRisks(requirementId);
      setRiskItems(resp.risks);
    } catch {
      /* risk loading is non-critical */
    }
  }, []);

  const reload = useCallback(async (targetRequirementId?: number | null) => {
    const requirementId = targetRequirementId ?? activeRequirementIdRef.current;
    beginSuppressCanvasSync();
    if (!requirementId) {
      domainNodesRef.current = [];
      setDomainNodes([]);
      setFocusedNodeId(null);
      setExpandedKeys([]);
      setRiskItems([]);
      return;
    }

    const tree = await fetchRuleTree(requirementId);
    if (activeRequirementIdRef.current !== requirementId) {
      return;
    }
    const normalizedNodes = tree.nodes.map((node) => ({
      ...node,
      content: normalizeRuleNodeContent(node.content),
    }));
    domainNodesRef.current = normalizedNodes;
    setDomainNodes(normalizedNodes);
    loadRisks(requirementId);
  }, [beginSuppressCanvasSync, loadRisks]);

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
      if (isReadonlyVersion) return;
      setEditingNode(domainNode);
      form.setFieldsValue(domainNode);
    },
    [form, isReadonlyVersion, nodeMap],
  );

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

  const runAIParse = async () => {
    const result = await aiParse(aiText);
    setAiDraft(result.nodes);
    setAiParseMode(result.analysis_mode);
  };

  const importAIDraft = async () => {
    if (!activeRequirementId) {
      message.warning("请先选择需求");
      return;
    }

    const idMap = new Map<string, string>();

    for (const draft of aiDraft) {
      const parentId = draft.parent_id ? idMap.get(draft.parent_id) || null : null;
      const created = await createRuleNode({
        requirement_id: activeRequirementId,
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
    } catch (error) {
      message.error(getErrorMessage(error, "版本对比失败"));
    } finally {
      setDiffLoading(false);
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
      const result = await generateRuleTreeSession(selectedSessionId, {
        requirement_text: sessionRequirementText.trim(),
        title: sessionTitleInput.trim() || undefined,
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
          <Space size={6}>
            <Button type="primary" onClick={() => setCreateOpen(true)}>
              新增节点
            </Button>
            <Button onClick={() => setAiOpen(true)}>AI 解析需求</Button>
          </Space>
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
            <div style={{ padding: 10, borderBottom: "1px solid #eef2f7" }}>
              <Typography.Text>
                当前选中：{focusedNodeId ? nodeMap.get(focusedNodeId)?.content || focusedNodeId : "-"}
              </Typography.Text>
            </div>
            <div style={{ flex: 1 }}>
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
                onDataChange={syncCanvasChanges}
              />
            </div>
          </div>

          {riskPanelVisible && (
            <div
              style={{
                width: 340,
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
              />
            </div>
          )}
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

      <Modal
        title="AI 解析需求"
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
                  <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>
                    {item.content.length > 500 ? `${item.content.slice(0, 500)}...` : item.content}
                  </Typography.Paragraph>
                </div>
              ))
            )}
          </Space>
        )}
      </Drawer>

      <Modal
        title="版本对比"
        open={diffOpen}
        onCancel={() => {
          setDiffOpen(false);
          setSemanticDiffResult(null);
        }}
        footer={null}
        width={980}
      >
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
          <>
            <Alert
              style={{ marginBottom: 12 }}
              type="info"
              message={`对比总结（v${semanticDiffResult.base_version} → v${semanticDiffResult.compare_version}）`}
              description={
                <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>
                  {semanticDiffResult.summary}
                </Typography.Paragraph>
              }
              showIcon
            />

            {semanticDiffResult.risk_notes && (
              <Alert
                style={{ marginBottom: 12 }}
                type="warning"
                message="风险提示"
                description={semanticDiffResult.risk_notes}
                showIcon
              />
            )}

            {semanticDiffResult.flow_changes.length === 0 ? (
              <Alert style={{ marginBottom: 12 }} type="success" message="两个版本无实质性流程差异" />
            ) : (
              <Table
                size="small"
                rowKey={(_, index) => String(index)}
                dataSource={semanticDiffResult.flow_changes}
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
        )}
      </Modal>
    </div>
  );
}
