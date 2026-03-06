import type { NodeType, RiskItem, RiskLevel, RuleNode } from "../../types";

export const VIRTUAL_ROOT_UID = "__virtual_root__";

export type MindMapNodeType = NodeType | "virtual";

export type MindMapNodeData = {
  text: string;
  uid: string;
  richText?: boolean;
  expand?: boolean;
  _nodeType?: MindMapNodeType;
  _riskLevel?: RiskLevel;
  _isVirtualRoot?: boolean;
  _riskWarning?: RiskLevel;
  shape?: string;
  fillColor?: string;
  color?: string;
  borderColor?: string;
  borderWidth?: number;
  borderDasharray?: string;
  borderRadius?: number;
  lineColor?: string;
  lineDasharray?: string;
};

export type MindMapTreeNode = {
  data: MindMapNodeData;
  children?: MindMapTreeNode[];
};

export type RuleNodeSnapshot = Pick<RuleNode, "id" | "parent_id" | "node_type" | "content" | "risk_level">;

const riskColors: Record<RiskLevel, string> = {
  critical: "#ff4d4f",
  high: "#fa8c16",
  medium: "#fadb14",
  low: "#52c41a",
};

let decodeEntityEl: HTMLTextAreaElement | null = null;
let htmlNormalizeEl: HTMLDivElement | null = null;

function decodeHtmlEntities(text: string): string {
  if (typeof document === "undefined") return text;
  if (!decodeEntityEl) {
    decodeEntityEl = document.createElement("textarea");
  }
  decodeEntityEl.innerHTML = text;
  return decodeEntityEl.value;
}

function extractTextFromHtml(html: string): string {
  if (typeof document === "undefined") return html;
  if (!htmlNormalizeEl) {
    htmlNormalizeEl = document.createElement("div");
  }
  // Keep line breaks when converting rich text html back to plain text.
  htmlNormalizeEl.innerHTML = html.replace(/<br\s*\/?>/gi, "\n");
  return (htmlNormalizeEl.textContent || "").replace(/\u00a0/g, " ");
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toRichTextHtml(text: string): string {
  const escaped = escapeHtml(text);
  return `<p>${escaped.replace(/\n/g, "<br/>")}</p>`;
}

export function normalizeRuleNodeContent(value: unknown): string {
  let normalized = String(value ?? "").trim();
  if (!normalized) return "未命名节点";

  // Handle multiple rounds of escaped entities like &amp;lt;...&amp;gt;.
  for (let i = 0; i < 6; i += 1) {
    const decoded = decodeHtmlEntities(normalized);
    if (decoded === normalized) break;
    normalized = decoded;
  }

  // If rich text HTML leaked into persisted content, recover plain text.
  if (/<\/?[a-zA-Z][^>]*>/.test(normalized)) {
    normalized = extractTextFromHtml(normalized).trim();
  }

  return normalized || "未命名节点";
}

function toSafeText(text: string): string {
  return normalizeRuleNodeContent(text);
}

function normalizeNodeType(nodeType: string | undefined, parentId: string | null): NodeType {
  if (nodeType === "root") return "root";
  if (nodeType === "condition") return "condition";
  if (nodeType === "branch") return "branch";
  if (nodeType === "action") return "action";
  if (nodeType === "exception") return "exception";
  return parentId ? "branch" : "root";
}

function normalizeRiskLevel(riskLevel: string | undefined): RiskLevel {
  if (riskLevel === "critical") return "critical";
  if (riskLevel === "high") return "high";
  if (riskLevel === "medium") return "medium";
  if (riskLevel === "low") return "low";
  return "medium";
}

function nodeVisual(nodeType: MindMapNodeType, riskLevel: RiskLevel): Partial<MindMapNodeData> {
  const riskColor = riskColors[riskLevel];

  if (nodeType === "virtual") {
    return {
      shape: "rectangle",
      fillColor: "#eef2ff",
      color: "#2f3f8f",
      borderColor: "#c7d2fe",
      borderWidth: 1,
      borderRadius: 8,
      lineColor: "#8ea0ff",
    };
  }

  if (nodeType === "root") {
    return {
      shape: "rectangle",
      fillColor: "#323b52",
      color: "#ffffff",
      borderColor: "#323b52",
      borderWidth: 1,
      borderRadius: 12,
      lineColor: "#6d7fb8",
    };
  }

  if (nodeType === "condition") {
    return {
      shape: "diamond",
      fillColor: "#4e6bff",
      color: "#ffffff",
      borderColor: riskColor,
      borderWidth: 2,
      borderRadius: 8,
      lineColor: "#6c7eff",
    };
  }

  if (nodeType === "exception") {
    return {
      shape: "rectangle",
      fillColor: "#fff8e8",
      color: "#6b5708",
      borderColor: riskColor,
      borderWidth: 2,
      borderDasharray: "6,4",
      borderRadius: 10,
      lineColor: "#f0b64b",
      lineDasharray: "6,4",
    };
  }

  if (nodeType === "action") {
    return {
      shape: "rectangle",
      fillColor: "#e8f8ef",
      color: "#1f5d39",
      borderColor: riskColor,
      borderWidth: 2,
      borderRadius: 10,
      lineColor: "#5dbb8a",
    };
  }

  return {
    shape: "rectangle",
    fillColor: "#eef2ff",
    color: "#2f3f8f",
    borderColor: riskColor,
    borderWidth: 2,
    borderRadius: 10,
    lineColor: "#7f90f6",
  };
}

const riskWarningColors: Record<RiskLevel, string> = {
  critical: "#ff4d4f",
  high: "#fa8c16",
  medium: "#fadb14",
  low: "#52c41a",
};

const RISK_LEVEL_WEIGHT: Record<RiskLevel, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};

export function buildNodeRiskMap(risks: RiskItem[]): Map<string, RiskLevel> {
  const map = new Map<string, RiskLevel>();
  for (const risk of risks) {
    if (!risk.related_node_id || risk.decision !== "pending") continue;
    const existing = map.get(risk.related_node_id);
    if (!existing || RISK_LEVEL_WEIGHT[risk.risk_level] > RISK_LEVEL_WEIGHT[existing]) {
      map.set(risk.related_node_id, risk.risk_level);
    }
  }
  return map;
}

function createMindMapNodeData(node: RuleNode, riskWarning?: RiskLevel): MindMapNodeData {
  const safeText = toSafeText(node.content);
  const warningPrefix = riskWarning
    ? `<span style="color:${riskWarningColors[riskWarning]};font-size:14px">⚠ </span>`
    : "";
  return {
    text: `<p>${warningPrefix}${escapeHtml(safeText).replace(/\n/g, "<br/>")}</p>`,
    richText: true,
    uid: node.id,
    expand: true,
    _nodeType: node.node_type,
    _riskLevel: node.risk_level,
    _riskWarning: riskWarning,
    ...nodeVisual(node.node_type, node.risk_level),
  };
}

export function ruleNodesToMindMapData(
  nodes: RuleNode[],
  nodeRiskMap?: Map<string, RiskLevel>,
): MindMapTreeNode {
  if (nodes.length === 0) {
    return {
      data: {
        text: toRichTextHtml("暂无规则节点"),
        richText: true,
        uid: VIRTUAL_ROOT_UID,
        _nodeType: "virtual",
        _riskLevel: "low",
        _isVirtualRoot: true,
        ...nodeVisual("virtual", "low"),
      },
      children: [],
    };
  }

  const nodeMap = new Map<string, RuleNode>();
  nodes.forEach((node) => nodeMap.set(node.id, node));

  const childrenMap = new Map<string | null, string[]>();
  const pushChild = (parentId: string | null, childId: string) => {
    const list = childrenMap.get(parentId) || [];
    list.push(childId);
    childrenMap.set(parentId, list);
  };

  nodes.forEach((node) => {
    const hasValidParent = !!node.parent_id && nodeMap.has(node.parent_id);
    pushChild(hasValidParent ? node.parent_id : null, node.id);
  });

  const buildTree = (nodeId: string, path: Set<string>): MindMapTreeNode => {
    const current = nodeMap.get(nodeId);
    if (!current) {
      return {
        data: {
          text: toRichTextHtml(nodeId),
          richText: true,
          uid: nodeId,
          _nodeType: "branch",
          _riskLevel: "medium",
          ...nodeVisual("branch", "medium"),
        },
        children: [],
      };
    }

    if (path.has(nodeId)) {
      return {
        data: {
          text: toRichTextHtml(`${toSafeText(current.content)} (循环引用)`),
          richText: true,
          uid: current.id,
          _nodeType: current.node_type,
          _riskLevel: current.risk_level,
          ...nodeVisual(current.node_type, current.risk_level),
        },
        children: [],
      };
    }

    const nextPath = new Set(path);
    nextPath.add(nodeId);

    const children = (childrenMap.get(nodeId) || []).map((childId) => buildTree(childId, nextPath));
    return {
      data: createMindMapNodeData(current, nodeRiskMap?.get(nodeId)),
      children,
    };
  };

  const rootIds = childrenMap.get(null) || [];
  const rootTrees = rootIds.map((rootId) => buildTree(rootId, new Set<string>()));

  if (rootTrees.length === 1) {
    return rootTrees[0];
  }

  return {
    data: {
      text: toRichTextHtml("规则树"),
      richText: true,
      uid: VIRTUAL_ROOT_UID,
      expand: true,
      _nodeType: "virtual",
      _riskLevel: "low",
      _isVirtualRoot: true,
      ...nodeVisual("virtual", "low"),
    },
    children: rootTrees,
  };
}

export function mindMapDataToRuleNodes(root: MindMapTreeNode): RuleNodeSnapshot[] {
  const result: RuleNodeSnapshot[] = [];
  const dedupe = new Set<string>();

  const walk = (node: MindMapTreeNode, parentId: string | null) => {
    const uid = String(node.data?.uid || "").trim();
    const text = toSafeText(node.data?.text || "");

    const isVirtualRoot = uid === VIRTUAL_ROOT_UID || node.data?._isVirtualRoot === true;
    let currentParentId = parentId;

    if (!isVirtualRoot) {
      if (!uid || dedupe.has(uid)) return;
      dedupe.add(uid);

      const nodeType = normalizeNodeType(node.data?._nodeType, parentId);
      const riskLevel = normalizeRiskLevel(node.data?._riskLevel);

      result.push({
        id: uid,
        parent_id: parentId,
        node_type: nodeType,
        content: text,
        risk_level: riskLevel,
      });
      currentParentId = uid;
    }

    (node.children || []).forEach((child) => walk(child, currentParentId));
  };

  walk(root, null);
  return result;
}
