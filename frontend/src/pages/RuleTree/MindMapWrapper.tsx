import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import MindMap from "simple-mind-map/full";
import "simple-mind-map/dist/simpleMindMap.esm.css";
import type { MindMapTreeNode } from "./dataAdapter";
import { VIRTUAL_ROOT_UID } from "./dataAdapter";
import { ensureRuleTreeTheme } from "./mindMapTheme";

export type MindMapLayout =
  | "logicalStructure"
  | "logicalStructureLeft"
  | "mindMap"
  | "organizationStructure"
  | "catalogOrganization"
  | "fishbone";

export type MindMapExportType = "png" | "svg" | "xmind" | "pdf" | "md";

type MindMapNodeInstance = {
  getData: (key: string) => unknown;
};

type MindMapRenderer = {
  findNodeByUid: (uid: string) => MindMapNodeInstance | null;
  moveNodeToCenter: (node: MindMapNodeInstance, resetScale?: boolean) => void;
  highlightNode: (node: MindMapNodeInstance, range?: unknown, style?: unknown) => void;
  closeHighlightNode: () => void;
};

export type MindMapWrapperRef = {
  exportAs: (type: MindMapExportType, fileName?: string) => Promise<void>;
  fitView: () => void;
  focusNode: (uid: string) => boolean;
  highlightNode: (uid: string) => boolean;
  clearHighlight: () => void;
};

type MindMapWrapperProps = {
  data: MindMapTreeNode;
  selectedNodeId: string | null;
  layout: MindMapLayout;
  theme: string;
  editable: boolean;
  textAutoWrapWidth?: number;
  autoFit?: boolean;
  onNodeClick?: (nodeId: string) => void;
  onNodeContextMenu?: (nodeId: string, position: { x: number; y: number }) => void;
  onDataChange?: (data: MindMapTreeNode) => void;
};

const MindMapWrapper = forwardRef<MindMapWrapperRef, MindMapWrapperProps>(function MindMapWrapper(props, ref) {
  const {
    data,
    selectedNodeId,
    layout,
    theme,
    editable,
    textAutoWrapWidth = 150,
    autoFit = false,
    onNodeClick,
    onNodeContextMenu,
    onDataChange,
  } = props;
  const scaleRatio = 0.1;
  const translateRatio = 0.38;
  const mousewheelMoveStep = 28;
  const minReadableScale = 0.6;
  const resolvedTextAutoWrapWidth = Math.max(80, textAutoWrapWidth);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const mindMapRef = useRef<any>(null);
  const applyingDataRef = useRef(false);
  const pendingDataRef = useRef<MindMapTreeNode | null>(null);
  const latestDataRef = useRef<MindMapTreeNode>(data);
  const selectedNodeIdRef = useRef<string | null>(selectedNodeId);
  const pendingViewportSyncRef = useRef(false);
  const onNodeClickRef = useRef(onNodeClick);
  const onNodeContextMenuRef = useRef(onNodeContextMenu);
  const onDataChangeRef = useRef(onDataChange);

  useEffect(() => {
    onNodeClickRef.current = onNodeClick;
  }, [onNodeClick]);

  useEffect(() => {
    onNodeContextMenuRef.current = onNodeContextMenu;
  }, [onNodeContextMenu]);

  useEffect(() => {
    onDataChangeRef.current = onDataChange;
  }, [onDataChange]);

  useEffect(() => {
    selectedNodeIdRef.current = selectedNodeId;
  }, [selectedNodeId]);

  useEffect(() => {
    latestDataRef.current = data;
  }, [data]);

  const getRenderer = (): MindMapRenderer | null => {
    const instance = mindMapRef.current;
    if (!instance) return null;
    return instance.renderer as unknown as MindMapRenderer;
  };

  const fitView = () => {
    mindMapRef.current?.view.fit(() => {}, true, 50);
  };

  const getCurrentScale = (): number => {
    const transformData = mindMapRef.current?.view?.getTransformData?.();
    const rawScale = Number(transformData?.transform?.scaleX ?? 1);
    return Number.isFinite(rawScale) ? rawScale : 1;
  };

  const ensureReadableScale = (preferredUid?: string | null): void => {
    if (getCurrentScale() >= minReadableScale) return;

    const fallbackUid = preferredUid || resolveFallbackFocusUid(latestDataRef.current);
    if (fallbackUid && focusNode(fallbackUid, true, true)) return;

    mindMapRef.current?.view?.setScale?.(1);
  };

  const resolveFallbackFocusUid = (tree: MindMapTreeNode): string | null => {
    const selectedUid = selectedNodeIdRef.current;
    if (selectedUid && selectedUid !== VIRTUAL_ROOT_UID) return selectedUid;

    const rootUid = String(tree?.data?.uid || "");
    if (rootUid && rootUid !== VIRTUAL_ROOT_UID) return rootUid;

    const firstChildUid = String(tree?.children?.[0]?.data?.uid || "");
    if (firstChildUid && firstChildUid !== VIRTUAL_ROOT_UID) return firstChildUid;

    return null;
  };

  const focusNode = (uid: string, moveToCenter: boolean, resetScale = false): boolean => {
    if (!uid || uid === VIRTUAL_ROOT_UID) return false;

    const instance = mindMapRef.current;
    const renderer = getRenderer();
    if (!instance || !renderer) return false;

    const node = renderer.findNodeByUid(uid);
    if (!node) return false;

    instance.execCommand("CLEAR_ACTIVE_NODE");
    instance.execCommand("SET_NODE_ACTIVE", node, true);

    if (moveToCenter) {
      renderer.moveNodeToCenter(node, resetScale);
    }

    return true;
  };

  const highlightNode = (uid: string): boolean => {
    if (!uid || uid === VIRTUAL_ROOT_UID) return false;
    const renderer = getRenderer();
    if (!renderer) return false;

    const node = renderer.findNodeByUid(uid);
    if (!node) return false;

    renderer.highlightNode(node, null, {
      stroke: "rgba(76, 99, 255, 0.75)",
      fill: "rgba(76, 99, 255, 0.06)",
    });
    return true;
  };

  useImperativeHandle(ref, () => ({
    exportAs: async (type: MindMapExportType, fileName = "规则树") => {
      const instance = mindMapRef.current;
      if (!instance) return;
      await instance.export(type, true, fileName);
    },
    fitView,
    focusNode: (uid: string) => focusNode(uid, true, false),
    highlightNode,
    clearHighlight: () => {
      getRenderer()?.closeHighlightNode();
    },
  }));

  useEffect(() => {
    if (!containerRef.current) return;

    ensureRuleTreeTheme(MindMap as unknown as { defineTheme: (name: string, config?: Record<string, unknown>) => Error | void });

    const instance = new (MindMap as any)({
      el: containerRef.current,
      data,
      layout,
      theme,
      fit: autoFit,
      textAutoWrapWidth: resolvedTextAutoWrapWidth,
      scaleRatio,
      translateRatio,
      mousewheelMoveStep,
      readonly: !editable,
      mousewheelAction: "move",
      mousewheelZoomActionReverse: false,
      isShowCreateChildBtnIcon: false,
      beforeShortcutRun: () => !editable,
    });

    const handleNodeClick = (node: MindMapNodeInstance) => {
      const uid = String(node?.getData?.("uid") || "");
      if (!uid || uid === VIRTUAL_ROOT_UID) return;
      onNodeClickRef.current?.(uid);
    };

    const handleNodeContextMenu = (e: MouseEvent, node: MindMapNodeInstance) => {
      e.preventDefault();
      const uid = String(node?.getData?.("uid") || "");
      if (!uid || uid === VIRTUAL_ROOT_UID) return;
      onNodeContextMenuRef.current?.(uid, { x: e.clientX, y: e.clientY });
    };

    const handleDataChange = (nextTree: MindMapTreeNode) => {
      if (applyingDataRef.current) return;
      onDataChangeRef.current?.(nextTree);
    };

    const handleNodeTreeRenderEnd = () => {
      if (pendingViewportSyncRef.current) {
        const focusUid = resolveFallbackFocusUid(latestDataRef.current);
        if (focusUid && focusNode(focusUid, true, true)) {
          pendingViewportSyncRef.current = false;
        }
      }
      ensureReadableScale(selectedNodeIdRef.current);
      applyingDataRef.current = false;

      const queued = pendingDataRef.current;
      if (queued) {
        pendingDataRef.current = null;
        applyingDataRef.current = true;
        pendingViewportSyncRef.current = true;
        instance.setData(queued);
      }
    };

    instance.on("node_click", handleNodeClick);
    instance.on("node_contextmenu", handleNodeContextMenu);
    instance.on("data_change", handleDataChange);
    instance.on("node_tree_render_end", handleNodeTreeRenderEnd);
    mindMapRef.current = instance;

    return () => {
      instance.off("node_click", handleNodeClick);
      instance.off("node_contextmenu", handleNodeContextMenu);
      instance.off("data_change", handleDataChange);
      instance.off("node_tree_render_end", handleNodeTreeRenderEnd);
      instance.destroy();
      mindMapRef.current = null;
    };
  }, [autoFit]);

  useEffect(() => {
    const instance = mindMapRef.current;
    if (!instance) return;
    instance.setLayout(layout);
  }, [layout]);

  useEffect(() => {
    const instance = mindMapRef.current;
    if (!instance) return;
    instance.setTheme(theme);
  }, [theme]);

  useEffect(() => {
    const instance = mindMapRef.current;
    if (!instance) return;
    instance.updateConfig({
      readonly: !editable,
      textAutoWrapWidth: resolvedTextAutoWrapWidth,
      scaleRatio,
      translateRatio,
      mousewheelMoveStep,
      mousewheelAction: "move",
      isShowCreateChildBtnIcon: false,
      beforeShortcutRun: () => !editable,
    });
    // simple-mind-map 的 updateConfig 只更新配置，不会自动触发重绘
    if (typeof instance.reRender === "function") {
      instance.reRender();
      return;
    }
    if (typeof instance.render === "function") {
      instance.render();
    }
  }, [editable, resolvedTextAutoWrapWidth]);

  useEffect(() => {
    const instance = mindMapRef.current;
    if (!instance) return;

    if (applyingDataRef.current) {
      pendingDataRef.current = data;
      return;
    }

    applyingDataRef.current = true;
    pendingViewportSyncRef.current = true;
    instance.setData(data);
  }, [data]);

  useEffect(() => {
    const renderer = getRenderer();
    if (!renderer) return;
    renderer.closeHighlightNode();

    if (!selectedNodeId) return;
    const shouldResetScale = pendingViewportSyncRef.current;
    if (!focusNode(selectedNodeId, true, shouldResetScale)) {
      pendingViewportSyncRef.current = true;
      return;
    }
    pendingViewportSyncRef.current = false;
    ensureReadableScale(selectedNodeId);
  }, [selectedNodeId]);

  return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
});

export default MindMapWrapper;
