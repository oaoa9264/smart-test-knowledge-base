import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import {
  batchDeleteTestCases,
  confirmImport,
  createTestCase,
  deleteTestCase,
  fetchTestCase,
  fetchTestCases,
  parseImportFile,
  updateTestCase,
} from "../../api/testcases";
import { fetchRuleTree } from "../../api/rules";
import { useAppStore } from "../../stores/appStore";
import type {
  ImportAnalysisMode,
  LLMStatus,
  ParsedCasePreview,
  RiskLevel,
  RuleNode,
  RulePath,
  TestCase,
} from "../../types";
import {
  getImportAnalysisModeLabel,
  getRiskLevelLabel,
  getTestCaseStatusLabel,
  riskLevelLabels,
} from "../../utils/enumLabels";

const { Dragger } = Upload;
const { Text } = Typography;

const riskTagColors: Record<RiskLevel, string> = {
  critical: "red",
  high: "volcano",
  medium: "gold",
  low: "green",
};

const confidenceTagColors: Record<string, string> = {
  high: "green",
  medium: "gold",
  low: "orange",
  none: "red",
};

const riskOptions = [
  { label: <Tag color={riskTagColors.critical}>严重</Tag>, value: "critical" },
  { label: <Tag color={riskTagColors.high}>高</Tag>, value: "high" },
  { label: <Tag color={riskTagColors.medium}>中</Tag>, value: "medium" },
  { label: <Tag color={riskTagColors.low}>低</Tag>, value: "low" },
];

const statusOptions = [
  { label: "有效", value: "active" },
  { label: "待复核", value: "needs_review" },
  { label: "已失效", value: "invalidated" },
];

interface ImportPreviewRow extends ParsedCasePreview {
  risk_level: RiskLevel;
  bound_rule_node_ids: string[];
  bound_path_ids: string[];
  skip_import: boolean;
}

const importSteps = [
  { title: "上传文件" },
  { title: "预览匹配" },
  { title: "确认导入" },
];

function formatImportAnalysisLabel(mode: ImportAnalysisMode, provider?: string | null): string {
  if (mode !== "llm") {
    return getImportAnalysisModeLabel(mode);
  }
  if (!provider) {
    return getImportAnalysisModeLabel(mode);
  }
  if (provider === "openai") {
    return `${getImportAnalysisModeLabel(mode)}（OpenAI）`;
  }
  if (provider === "zhipu") {
    return `${getImportAnalysisModeLabel(mode)}（GLM/智谱）`;
  }
  return `${getImportAnalysisModeLabel(mode)}（${provider}）`;
}

function getErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  return fallback;
}

export default function TestCasesPage() {
  const location = useLocation();
  const { selectedProjectId, selectedRequirementId, requirements } = useAppStore();

  const [form] = Form.useForm();
  const selectedNodeIds = Form.useWatch<string[]>("bound_rule_node_ids", form) || [];
  const [editForm] = Form.useForm();
  const selectedEditNodeIds = Form.useWatch<string[]>("bound_rule_node_ids", editForm) || [];

  const [cases, setCases] = useState<TestCase[]>([]);
  const [casesLoaded, setCasesLoaded] = useState(false);
  const [highlightedCaseId, setHighlightedCaseId] = useState<number | null>(null);
  const [nodes, setNodes] = useState<RuleNode[]>([]);
  const [paths, setPaths] = useState<RulePath[]>([]);
  const [viewingCase, setViewingCase] = useState<TestCase | null>(null);
  const [editingCase, setEditingCase] = useState<TestCase | null>(null);
  const [viewLoading, setViewLoading] = useState(false);
  const [deletingCaseId, setDeletingCaseId] = useState<number | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [createFormCollapsed, setCreateFormCollapsed] = useState(true);
  const [selectedCaseIds, setSelectedCaseIds] = useState<number[]>([]);
  const [batchDeleting, setBatchDeleting] = useState(false);

  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importStep, setImportStep] = useState(0);
  const [importRequirementId, setImportRequirementId] = useState<number | null>(null);
  const [importFileList, setImportFileList] = useState<UploadFile[]>([]);
  const [importParsing, setImportParsing] = useState(false);
  const [importConfirming, setImportConfirming] = useState(false);
  const [importRows, setImportRows] = useState<ImportPreviewRow[]>([]);
  const [importAnalysisMode, setImportAnalysisMode] = useState<ImportAnalysisMode>("mock_fallback");
  const [importLlmStatus, setImportLlmStatus] = useState<LLMStatus | null>(null);
  const [importLlmProvider, setImportLlmProvider] = useState<string | null>(null);
  const [importLlmMessage, setImportLlmMessage] = useState<string | null>(null);
  const [importSelectedRowKeys, setImportSelectedRowKeys] = useState<number[]>([]);
  const [batchRiskLevel, setBatchRiskLevel] = useState<RiskLevel>("medium");
  const [importNodes, setImportNodes] = useState<RuleNode[]>([]);
  const [importPaths, setImportPaths] = useState<RulePath[]>([]);
  const [importTreeLoading, setImportTreeLoading] = useState(false);

  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    const focusCaseId = searchParams.get("focusCaseId");
    if (!focusCaseId) {
      setHighlightedCaseId(null);
      return;
    }

    const parsed = Number(focusCaseId);
    if (Number.isInteger(parsed) && parsed > 0) {
      setHighlightedCaseId(parsed);
      return;
    }

    setHighlightedCaseId(null);
  }, [location.search]);

  useEffect(() => {
    if (!selectedProjectId || !selectedRequirementId) {
      setCases([]);
      setCasesLoaded(false);
      return;
    }

    setCasesLoaded(false);
    fetchTestCases(selectedProjectId, selectedRequirementId)
      .then((data) => {
        setCases(data);
        setCasesLoaded(true);
      })
      .catch(() => {
        setCasesLoaded(true);
        message.error("加载用例失败");
      });
  }, [selectedProjectId, selectedRequirementId]);

  useEffect(() => {
    if (!casesLoaded || highlightedCaseId === null) {
      return;
    }

    const targetExists = cases.some((item) => item.id === highlightedCaseId);
    if (!targetExists) {
      message.warning(`未找到用例 #${highlightedCaseId}，请确认当前需求下是否存在该用例`);
      setHighlightedCaseId(null);
      return;
    }

    const timer = window.setTimeout(() => {
      const targetRow = document.querySelector(`tr[data-row-key="${highlightedCaseId}"]`);
      if (targetRow instanceof HTMLElement) {
        targetRow.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 100);
    return () => window.clearTimeout(timer);
  }, [cases, casesLoaded, highlightedCaseId]);

  useEffect(() => {
    if (highlightedCaseId === null) {
      return;
    }
    const timer = window.setTimeout(() => {
      setHighlightedCaseId(null);
    }, 8000);
    return () => window.clearTimeout(timer);
  }, [highlightedCaseId]);

  useEffect(() => {
    if (!selectedRequirementId) {
      setNodes([]);
      setPaths([]);
      return;
    }

    fetchRuleTree(selectedRequirementId)
      .then((tree) => {
        setNodes(tree.nodes);
        setPaths(tree.paths);
      })
      .catch(() => message.error("加载规则树失败"));
  }, [selectedRequirementId]);

  useEffect(() => {
    form.setFieldsValue({ bound_rule_node_ids: [], bound_path_ids: [] });
  }, [form, selectedRequirementId]);

  useEffect(() => {
    setEditingCase(null);
    editForm.resetFields();
  }, [editForm, selectedRequirementId]);

  useEffect(() => {
    if (!importModalOpen || !importRequirementId) {
      setImportNodes([]);
      setImportPaths([]);
      return;
    }

    setImportTreeLoading(true);
    fetchRuleTree(importRequirementId)
      .then((tree) => {
        setImportNodes(tree.nodes);
        setImportPaths(tree.paths);
      })
      .catch(() => {
        message.error("加载导入目标规则树失败");
        setImportNodes([]);
        setImportPaths([]);
      })
      .finally(() => setImportTreeLoading(false));
  }, [importModalOpen, importRequirementId]);

  const nodeMap = useMemo(() => {
    const map = new Map<string, RuleNode>();
    nodes.forEach((item) => map.set(item.id, item));
    return map;
  }, [nodes]);

  const pathMap = useMemo(() => {
    const map = new Map<string, RulePath>();
    paths.forEach((item) => map.set(item.id, item));
    return map;
  }, [paths]);

  const importNodeMap = useMemo(() => {
    const map = new Map<string, RuleNode>();
    importNodes.forEach((item) => map.set(item.id, item));
    return map;
  }, [importNodes]);

  const getNodeDisplay = (nodeId: string) => nodeMap.get(nodeId)?.content || nodeId;
  const getPathDisplay = (pathId: string) => {
    const path = pathMap.get(pathId);
    if (!path) {
      return pathId;
    }
    return path.node_sequence.map((nodeId) => getNodeDisplay(nodeId)).join(" -> ");
  };

  const getRiskTagColor = (risk?: string) =>
    risk ? riskTagColors[risk as RiskLevel] || "default" : "default";

  const renderEllipsisCell = (value?: string, maxWidth = 260) => {
    const text = value?.trim() || "-";
    return (
      <Tooltip title={text === "-" ? undefined : text}>
        <div
          style={{
            maxWidth,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {text}
        </div>
      </Tooltip>
    );
  };

  const getMatchedPathIdSet = (nodeIds: string[]) => {
    if (!nodeIds.length) {
      return new Set(paths.map((item) => item.id));
    }
    return new Set(
      paths
        .filter((item) => nodeIds.every((nodeId) => item.node_sequence.includes(nodeId)))
        .map((item) => item.id),
    );
  };

  const matchedPathIdSet = useMemo(() => getMatchedPathIdSet(selectedNodeIds), [paths, selectedNodeIds]);
  const matchedEditPathIdSet = useMemo(
    () => getMatchedPathIdSet(selectedEditNodeIds),
    [paths, selectedEditNodeIds],
  );

  useEffect(() => {
    const selectedPathIds = form.getFieldValue("bound_path_ids") || [];
    const filteredPathIds = selectedPathIds.filter((pathId: string) => matchedPathIdSet.has(pathId));
    if (filteredPathIds.length !== selectedPathIds.length) {
      form.setFieldsValue({ bound_path_ids: filteredPathIds });
      message.warning("已移除与已选规则节点不匹配的规则路径");
    }
    form.validateFields(["bound_path_ids"]).catch(() => undefined);
  }, [form, matchedPathIdSet]);

  useEffect(() => {
    if (!editingCase) {
      return;
    }
    const selectedPathIds = editForm.getFieldValue("bound_path_ids") || [];
    const filteredPathIds = selectedPathIds.filter((pathId: string) => matchedEditPathIdSet.has(pathId));
    if (filteredPathIds.length !== selectedPathIds.length) {
      editForm.setFieldsValue({ bound_path_ids: filteredPathIds });
      message.warning("已移除与已选规则节点不匹配的规则路径");
    }
    editForm.validateFields(["bound_path_ids"]).catch(() => undefined);
  }, [editForm, matchedEditPathIdSet, editingCase]);

  const nodeOptions = useMemo(
    () =>
      nodes.map((item) => ({
        label: `${item.content} (${riskLevelLabels[item.risk_level]})`,
        value: item.id,
      })),
    [nodes],
  );

  const createPathOptions = useMemo(
    () =>
      paths
        .map((item) => ({
          label: item.node_sequence.map((nodeId) => nodeMap.get(nodeId)?.content || nodeId).join(" -> "),
          value: item.id,
        }))
        .filter((item) => matchedPathIdSet.has(item.value)),
    [paths, nodeMap, matchedPathIdSet],
  );

  const editPathOptions = useMemo(
    () =>
      paths
        .map((item) => ({
          label: item.node_sequence.map((nodeId) => nodeMap.get(nodeId)?.content || nodeId).join(" -> "),
          value: item.id,
        }))
        .filter((item) => matchedEditPathIdSet.has(item.value)),
    [paths, nodeMap, matchedEditPathIdSet],
  );

  const importNodeOptions = useMemo(
    () =>
      importNodes.map((item) => ({
        label: `${item.content} (${riskLevelLabels[item.risk_level]})`,
        value: item.id,
      })),
    [importNodes],
  );

  const getImportPathOptions = (nodeIds: string[]) =>
    importPaths
      .filter((path) => nodeIds.every((nodeId) => path.node_sequence.includes(nodeId)))
      .map((path) => ({
        label: path.node_sequence.map((nodeId) => importNodeMap.get(nodeId)?.content || nodeId).join(" -> "),
        value: path.id,
      }));

  const importSummary = useMemo(() => {
    const total = importRows.length;
    const skipped = importRows.filter((item) => item.skip_import).length;
    const importable = total - skipped;
    const unbound = importRows.filter((item) => !item.skip_import && item.bound_rule_node_ids.length === 0).length;
    const autoMatched = importRows.filter((item) => item.matched_node_ids.length > 0 && item.confidence !== "none").length;
    return {
      total,
      skipped,
      importable,
      unbound,
      autoMatched,
      needReview: total - autoMatched,
    };
  }, [importRows]);

  const requirementOptions = useMemo(() => {
    const filtered = requirements.filter(
      (item) => !selectedProjectId || item.project_id === selectedProjectId,
    );
    const maxVersionByGroup = new Map<number, number>();
    for (const item of filtered) {
      if (item.requirement_group_id != null) {
        const cur = maxVersionByGroup.get(item.requirement_group_id) ?? 0;
        if (item.version > cur) maxVersionByGroup.set(item.requirement_group_id, item.version);
      }
    }
    return filtered.map((item) => {
      const isLatest =
        item.requirement_group_id != null &&
        item.version === maxVersionByGroup.get(item.requirement_group_id);
      const suffix = isLatest ? `v${item.version}(最新)` : `v${item.version}`;
      return { label: `${item.title} ${suffix}`, value: item.id };
    });
  }, [requirements, selectedProjectId]);

  const submit = async () => {
    if (!selectedProjectId) {
      message.warning("请先选择项目");
      return;
    }

    const values = await form.validateFields();
    const created = await createTestCase({ project_id: selectedProjectId, ...values });
    setCases((prev) => [created, ...prev]);
    form.resetFields();
    message.success("测试用例已创建");
  };

  const viewCase = async (caseId: number) => {
    setViewLoading(true);
    setViewingCase(null);
    try {
      const detail = await fetchTestCase(caseId);
      setViewingCase(detail);
    } catch {
      message.error("加载用例详情失败");
    } finally {
      setViewLoading(false);
    }
  };

  const startEdit = (row: TestCase) => {
    setEditingCase(row);
    editForm.setFieldsValue({
      title: row.title,
      precondition: row.precondition || "",
      steps: row.steps,
      expected_result: row.expected_result,
      risk_level: row.risk_level,
      status: row.status,
      bound_rule_node_ids: row.bound_rule_node_ids,
      bound_path_ids: row.bound_path_ids,
    });
  };

  const closeEdit = () => {
    setEditingCase(null);
    editForm.resetFields();
  };

  const submitEdit = async () => {
    if (!editingCase) {
      return;
    }

    const values = await editForm.validateFields();
    setEditSubmitting(true);
    try {
      const updated = await updateTestCase(editingCase.id, values);
      setCases((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      if (viewingCase?.id === updated.id) {
        setViewingCase(updated);
      }
      message.success("用例已更新");
      closeEdit();
    } catch {
      message.error("更新失败");
    } finally {
      setEditSubmitting(false);
    }
  };

  const removeCase = async (caseId: number) => {
    setDeletingCaseId(caseId);
    try {
      await deleteTestCase(caseId);
      setCases((prev) => prev.filter((item) => item.id !== caseId));
      setSelectedCaseIds((prev) => prev.filter((id) => id !== caseId));
      if (viewingCase?.id === caseId) {
        setViewingCase(null);
      }
      message.success("用例已删除");
    } catch {
      message.error("删除失败");
    } finally {
      setDeletingCaseId(null);
    }
  };

  const batchRemoveCases = async () => {
    if (!selectedCaseIds.length) {
      message.warning("请先选择要删除的用例");
      return;
    }
    setBatchDeleting(true);
    try {
      const result = await batchDeleteTestCases(selectedCaseIds);
      const deletedSet = new Set(selectedCaseIds);
      setCases((prev) => prev.filter((item) => !deletedSet.has(item.id)));
      if (viewingCase && deletedSet.has(viewingCase.id)) {
        setViewingCase(null);
      }
      setSelectedCaseIds([]);
      message.success(`已删除 ${result.deleted_count} 条用例`);
    } catch {
      message.error("批量删除失败");
    } finally {
      setBatchDeleting(false);
    }
  };

  const openImportModal = () => {
    if (!selectedProjectId) {
      message.warning("请先选择项目");
      return;
    }
    if (!selectedRequirementId) {
      message.warning("请先选择需求");
      return;
    }

    setImportModalOpen(true);
    setImportStep(0);
    setImportRequirementId(selectedRequirementId);
    setImportFileList([]);
    setImportRows([]);
    setImportSelectedRowKeys([]);
    setBatchRiskLevel("medium");
    setImportAnalysisMode("mock_fallback");
    setImportLlmStatus(null);
    setImportLlmProvider(null);
    setImportLlmMessage(null);
  };

  const closeImportModal = () => {
    if (importParsing || importConfirming) {
      return;
    }
    setImportModalOpen(false);
    setImportStep(0);
    setImportFileList([]);
    setImportRows([]);
    setImportSelectedRowKeys([]);
    setImportRequirementId(selectedRequirementId);
    setImportAnalysisMode("mock_fallback");
    setImportLlmStatus(null);
    setImportLlmProvider(null);
    setImportLlmMessage(null);
  };

  const handleParseImport = async () => {
    if (!importRequirementId) {
      message.warning("请选择关联需求");
      return;
    }

    const firstFile = importFileList[0];
    const fileObj = firstFile?.originFileObj ?? (firstFile as unknown as File | undefined);
    if (!(fileObj instanceof File)) {
      message.warning("请先上传 Excel 或 XMind 文件");
      return;
    }

    setImportParsing(true);
    try {
      const result = await parseImportFile(fileObj as File, importRequirementId);
      const rows: ImportPreviewRow[] = result.parsed_cases.map((item) => ({
        ...item,
        risk_level: item.suggested_risk_level || "medium",
        bound_rule_node_ids: item.matched_node_ids,
        bound_path_ids: [],
        skip_import: false,
      }));
      setImportRows(rows);
      setImportAnalysisMode(result.analysis_mode);
      setImportLlmStatus(result.llm_status || null);
      setImportLlmProvider(result.llm_provider || null);
      setImportLlmMessage(result.llm_message || null);
      setImportSelectedRowKeys(rows.map((item) => item.index));
      setImportStep(1);
      if (result.llm_status === "failed" || result.analysis_mode === "llm_failed") {
        message.warning(result.llm_message || "所有模型调用失败，未生成结果");
      } else {
        message.success(`解析完成，共 ${result.total_cases} 条`);
      }
    } catch (error) {
      message.error(getErrorMessage(error, "解析失败"));
    } finally {
      setImportParsing(false);
    }
  };

  const updateImportRow = (rowIndex: number, updater: (row: ImportPreviewRow) => ImportPreviewRow) => {
    setImportRows((prev) => prev.map((item) => (item.index === rowIndex ? updater(item) : item)));
  };

  const handleImportNodeChange = (row: ImportPreviewRow, nodeIds: string[]) => {
    const matchedPathIdSet = new Set(
      importPaths
        .filter((path) => nodeIds.every((nodeId) => path.node_sequence.includes(nodeId)))
        .map((path) => path.id),
    );
    updateImportRow(row.index, (current) => ({
      ...current,
      bound_rule_node_ids: nodeIds,
      bound_path_ids: current.bound_path_ids.filter((pathId) => matchedPathIdSet.has(pathId)),
    }));
  };

  const handleApplyBatchRisk = () => {
    if (!importSelectedRowKeys.length) {
      message.warning("请先选择至少一条用例");
      return;
    }

    setImportRows((prev) =>
      prev.map((item) =>
        importSelectedRowKeys.includes(item.index)
          ? {
              ...item,
              risk_level: batchRiskLevel,
            }
          : item,
      ),
    );
    message.success("已批量更新风险等级");
  };

  const toStepConfirm = () => {
    if (!importRows.length) {
      message.warning("暂无可导入数据");
      return;
    }
    setImportStep(2);
  };

  const refreshCaseList = async () => {
    if (!selectedProjectId) {
      return;
    }
    try {
      const data = await fetchTestCases(selectedProjectId, selectedRequirementId || undefined);
      setCases(data);
    } catch {
      message.error("刷新用例列表失败");
    }
  };

  const handleConfirmImport = async () => {
    if (!selectedProjectId || !importRequirementId) {
      message.warning("请先选择项目和需求");
      return;
    }

    if (importSummary.unbound > 0) {
      message.error("存在未绑定规则节点的用例，请先绑定或标记为跳过");
      return;
    }

    setImportConfirming(true);
    try {
      const resp = await confirmImport({
        project_id: selectedProjectId,
        requirement_id: importRequirementId,
        cases: importRows.map((item) => ({
          title: item.title,
          steps: item.steps,
          expected_result: item.expected_result,
          risk_level: item.risk_level,
          bound_rule_node_ids: item.bound_rule_node_ids,
          bound_path_ids: item.bound_path_ids,
          skip_import: item.skip_import,
        })),
      });
      message.success(`导入完成：成功 ${resp.imported_count}，跳过 ${resp.skipped_count}`);
      closeImportModal();
      await refreshCaseList();
    } catch (error) {
      message.error(getErrorMessage(error, "导入失败"));
    } finally {
      setImportConfirming(false);
    }
  };

  const importFooter =
    importStep === 0
      ? [
          <Button key="cancel" onClick={closeImportModal} disabled={importParsing}>
            取消
          </Button>,
          <Button key="parse" type="primary" loading={importParsing} onClick={handleParseImport}>
            开始解析
          </Button>,
        ]
      : importStep === 1
        ? [
            <Button key="cancel" onClick={closeImportModal} disabled={importParsing}>
              取消
            </Button>,
            <Button key="back" onClick={() => setImportStep(0)}>
              上一步
            </Button>,
            <Button key="next" type="primary" onClick={toStepConfirm}>
              下一步
            </Button>,
          ]
        : [
            <Button key="cancel" onClick={closeImportModal} disabled={importConfirming}>
              取消
            </Button>,
            <Button key="back" onClick={() => setImportStep(1)} disabled={importConfirming}>
              上一步
            </Button>,
            <Button
              key="confirm"
              type="primary"
              loading={importConfirming}
              onClick={handleConfirmImport}
              disabled={importSummary.unbound > 0}
            >
              确认导入
            </Button>,
          ];

  return (
    <div>
      {!selectedProjectId || !selectedRequirementId ? (
        <Alert type="info" message="请先在顶部选择项目和需求" style={{ marginBottom: 12 }} />
      ) : null}

      <Row gutter={16}>
        <Col span={createFormCollapsed ? 0 : 10} style={{ display: createFormCollapsed ? "none" : undefined }}>
          <Card title="新建测试用例">
            <Form
              form={form}
              layout="vertical"
              initialValues={{ risk_level: "medium", status: "active", precondition: "", bound_rule_node_ids: [], bound_path_ids: [] }}
            >
              <Form.Item name="title" label="用例标题" rules={[{ required: true, message: "请输入标题" }]}>
                <Input />
              </Form.Item>
              <Form.Item name="precondition" label="前置条件">
                <Input.TextArea rows={3} placeholder="如：存在一个客户，客户类型=代理商" />
              </Form.Item>
              <Form.Item name="steps" label="执行步骤" rules={[{ required: true, message: "请输入步骤" }]}>
                <Input.TextArea rows={4} />
              </Form.Item>
              <Form.Item name="expected_result" label="预期结果" rules={[{ required: true, message: "请输入预期结果" }]}>
                <Input.TextArea rows={3} />
              </Form.Item>
              <Form.Item name="risk_level" label="风险等级" rules={[{ required: true }]}>
                <Select options={riskOptions} />
              </Form.Item>
              <Form.Item name="status" label="状态" rules={[{ required: true }]}>
                <Select options={statusOptions} />
              </Form.Item>
              <Form.Item
                name="bound_rule_node_ids"
                label="绑定规则节点"
                rules={[{ required: true, message: "至少选择一个规则节点" }]}
              >
                <Select mode="multiple" options={nodeOptions} />
              </Form.Item>
              <Form.Item
                name="bound_path_ids"
                label="绑定规则路径"
                dependencies={["bound_rule_node_ids"]}
                rules={[
                  {
                    validator: async (_, value: string[] = []) => {
                      if (!value.length) {
                        return;
                      }
                      const hasInvalid = value.some((pathId) => !matchedPathIdSet.has(pathId));
                      if (hasInvalid) {
                        throw new Error("所选规则路径需包含已选择的全部规则节点");
                      }
                    },
                  },
                ]}
              >
                <Select mode="multiple" options={createPathOptions} />
              </Form.Item>
              <Button type="primary" onClick={submit} block>
                创建用例
              </Button>
            </Form>
          </Card>
        </Col>

        <Col span={createFormCollapsed ? 24 : 14}>
          <Card
            title="用例列表"
            extra={
              <Space>
                <Popconfirm
                  title={`确认删除选中的 ${selectedCaseIds.length} 条用例吗？`}
                  okText="删除"
                  cancelText="取消"
                  onConfirm={batchRemoveCases}
                  disabled={!selectedCaseIds.length}
                >
                  <Button danger loading={batchDeleting} disabled={!selectedCaseIds.length}>
                    批量删除{selectedCaseIds.length > 0 ? ` (${selectedCaseIds.length})` : ""}
                  </Button>
                </Popconfirm>
                <Button type="primary" onClick={openImportModal}>
                  导入用例
                </Button>
                <Button type="link" onClick={() => setCreateFormCollapsed((prev) => !prev)}>
                  {createFormCollapsed ? "展开新建用例" : "收起新建用例"}
                </Button>
              </Space>
            }
          >
            <Table<TestCase>
              rowKey="id"
              rowSelection={{
                selectedRowKeys: selectedCaseIds,
                onChange: (keys) => setSelectedCaseIds(keys as number[]),
              }}
              rowClassName={(row) => (row.id === highlightedCaseId ? "focus-case-row" : "")}
              size="small"
              pagination={{ pageSize: 8 }}
              scroll={{ x: createFormCollapsed ? 1450 : 1650 }}
              dataSource={cases}
              columns={[
                { title: "ID", dataIndex: "id", width: 70 },
                {
                  title: "标题",
                  dataIndex: "title",
                  width: 180,
                  render: (title: string) => renderEllipsisCell(title, 160),
                },
                {
                  title: "执行步骤",
                  dataIndex: "steps",
                  width: 280,
                  render: (steps: string) => renderEllipsisCell(steps, 260),
                },
                {
                  title: "预期结果",
                  dataIndex: "expected_result",
                  width: 280,
                  render: (expectedResult: string) => renderEllipsisCell(expectedResult, 260),
                },
                {
                  title: "绑定节点",
                  width: 280,
                  render: (_, row) =>
                    renderEllipsisCell(
                      row.bound_rule_node_ids.length
                        ? row.bound_rule_node_ids.map((nodeId) => getNodeDisplay(nodeId)).join(" | ")
                        : "-",
                      260,
                    ),
                },
                {
                  title: "风险",
                  dataIndex: "risk_level",
                  width: 120,
                  render: (risk) => <Tag color={getRiskTagColor(risk)}>{getRiskLevelLabel(risk)}</Tag>,
                },
                {
                  title: "状态",
                  dataIndex: "status",
                  width: 150,
                  render: (status) => (
                    <Tag color={status === "invalidated" ? "red" : status === "needs_review" ? "orange" : "green"}>
                      {getTestCaseStatusLabel(status)}
                    </Tag>
                  ),
                },
                {
                  title: "节点数",
                  render: (_, row) => row.bound_rule_node_ids.length,
                  width: 120,
                },
                {
                  title: "操作",
                  width: 220,
                  render: (_, row) => (
                    <Space size="small">
                      <Button type="link" onClick={() => startEdit(row)}>
                        修改
                      </Button>
                      <Button type="link" loading={viewLoading} onClick={() => viewCase(row.id)}>
                        查看
                      </Button>
                      <Popconfirm
                        title="确认删除该用例吗？"
                        okText="删除"
                        cancelText="取消"
                        onConfirm={() => removeCase(row.id)}
                      >
                        <Button type="link" danger loading={deletingCaseId === row.id}>
                          删除
                        </Button>
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        open={importModalOpen}
        title="测试用例智能导入"
        width={1200}
        onCancel={closeImportModal}
        footer={importFooter}
        destroyOnClose
      >
        <Steps current={importStep} items={importSteps} style={{ marginBottom: 20 }} />

        {importStep === 0 ? (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <Form layout="vertical">
              <Form.Item label="关联需求" required>
                <Select
                  value={importRequirementId ?? undefined}
                  onChange={(value) => setImportRequirementId(value)}
                  options={requirementOptions}
                  placeholder="请选择需求"
                />
              </Form.Item>
            </Form>

            <Dragger
              accept=".xlsx,.xlsm,.xmind"
              multiple={false}
              maxCount={1}
              fileList={importFileList}
              beforeUpload={(file) => {
                setImportFileList([
                  {
                    uid: file.uid,
                    name: file.name,
                    status: "done",
                    originFileObj: file,
                  },
                ]);
                return false;
              }}
              onRemove={() => {
                setImportFileList([]);
                return true;
              }}
            >
              <p className="ant-upload-drag-icon">
                <Text strong>拖拽文件到此处，或点击上传</Text>
              </p>
              <p className="ant-upload-text">支持 .xlsx / .xlsm / .xmind</p>
            </Dragger>

            <Alert
              type="info"
              showIcon
              message="解析说明"
              description="系统会先解析文件，再尝试将用例自动匹配到当前需求规则树节点。"
            />
          </Space>
        ) : null}

        {importStep === 1 ? (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {importLlmStatus === "failed" ? (
              <Alert
                type="warning"
                showIcon
                message="所有模型调用失败"
                description={importLlmMessage || "所有模型调用失败，未生成结果。请稍后重试或检查模型配置。"}
              />
            ) : null}

            <Alert
              type="info"
              showIcon
              message={`解析模式：${formatImportAnalysisLabel(importAnalysisMode, importLlmProvider)}`}
              description={`共 ${importSummary.total} 条，自动匹配 ${importSummary.autoMatched} 条，待复核 ${importSummary.needReview} 条`}
            />

            <Space>
              <Button onClick={() => setImportSelectedRowKeys(importRows.map((item) => item.index))}>全选</Button>
              <Button
                onClick={() => {
                  const selectedSet = new Set(importSelectedRowKeys);
                  const nextKeys = importRows
                    .map((item) => item.index)
                    .filter((index) => !selectedSet.has(index));
                  setImportSelectedRowKeys(nextKeys);
                }}
              >
                反选
              </Button>
              <Select<RiskLevel>
                value={batchRiskLevel}
                onChange={(value) => setBatchRiskLevel(value)}
                style={{ width: 140 }}
                options={[
                  { label: "严重", value: "critical" },
                  { label: "高", value: "high" },
                  { label: "中", value: "medium" },
                  { label: "低", value: "low" },
                ]}
              />
              <Button onClick={handleApplyBatchRisk}>批量设置风险等级</Button>
            </Space>

            <Table<ImportPreviewRow>
              rowKey="index"
              loading={importTreeLoading}
              size="small"
              pagination={{ pageSize: 8 }}
              scroll={{ x: 1800 }}
              dataSource={importRows}
              rowSelection={{
                selectedRowKeys: importSelectedRowKeys,
                onChange: (keys) => setImportSelectedRowKeys(keys as number[]),
              }}
              rowClassName={(row) =>
                !row.skip_import && row.bound_rule_node_ids.length === 0 ? "import-unbound-row" : ""
              }
              columns={[
                {
                  title: "标题",
                  dataIndex: "title",
                  width: 180,
                  render: (title: string) => renderEllipsisCell(title, 160),
                },
                {
                  title: "步骤",
                  dataIndex: "steps",
                  width: 220,
                  render: (steps: string) => renderEllipsisCell(steps, 200),
                },
                {
                  title: "预期结果",
                  dataIndex: "expected_result",
                  width: 220,
                  render: (expected: string) => renderEllipsisCell(expected, 200),
                },
                {
                  title: "匹配节点",
                  width: 320,
                  render: (_, row) => (
                    <Select
                      mode="multiple"
                      value={row.bound_rule_node_ids}
                      options={importNodeOptions}
                      onChange={(value) => handleImportNodeChange(row, value)}
                      style={{ width: "100%" }}
                      placeholder="请选择规则节点"
                    />
                  ),
                },
                {
                  title: "绑定路径",
                  width: 320,
                  render: (_, row) => (
                    <Select
                      mode="multiple"
                      value={row.bound_path_ids}
                      options={getImportPathOptions(row.bound_rule_node_ids)}
                      onChange={(value) =>
                        updateImportRow(row.index, (current) => ({
                          ...current,
                          bound_path_ids: value,
                        }))
                      }
                      style={{ width: "100%" }}
                      placeholder="可选：绑定规则路径"
                    />
                  ),
                },
                {
                  title: "置信度",
                  width: 110,
                  dataIndex: "confidence",
                  render: (confidence: string) => (
                    <Tag color={confidenceTagColors[confidence] || "default"}>{confidence}</Tag>
                  ),
                },
                {
                  title: "匹配理由",
                  dataIndex: "match_reason",
                  width: 220,
                  render: (reason: string) => renderEllipsisCell(reason, 200),
                },
                {
                  title: "风险等级",
                  width: 130,
                  render: (_, row) => (
                    <Select<RiskLevel>
                      value={row.risk_level}
                      options={[
                        { label: "严重", value: "critical" },
                        { label: "高", value: "high" },
                        { label: "中", value: "medium" },
                        { label: "低", value: "low" },
                      ]}
                      onChange={(value) =>
                        updateImportRow(row.index, (current) => ({
                          ...current,
                          risk_level: value,
                        }))
                      }
                      style={{ width: "100%" }}
                    />
                  ),
                },
                {
                  title: "跳过导入",
                  width: 120,
                  render: (_, row) => (
                    <Checkbox
                      checked={row.skip_import}
                      onChange={(event) =>
                        updateImportRow(row.index, (current) => ({
                          ...current,
                          skip_import: event.target.checked,
                        }))
                      }
                    />
                  ),
                },
              ]}
            />
          </Space>
        ) : null}

        {importStep === 2 ? (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {importLlmStatus === "failed" ? (
              <Alert
                type="warning"
                showIcon
                message="所有模型调用失败"
                description={importLlmMessage || "所有模型调用失败，未生成结果。请稍后重试或检查模型配置。"}
              />
            ) : null}

            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label="解析模式">
                {formatImportAnalysisLabel(importAnalysisMode, importLlmProvider)}
              </Descriptions.Item>
              <Descriptions.Item label="总数">{importSummary.total}</Descriptions.Item>
              <Descriptions.Item label="自动匹配">{importSummary.autoMatched}</Descriptions.Item>
              <Descriptions.Item label="待复核">{importSummary.needReview}</Descriptions.Item>
              <Descriptions.Item label="将导入">{importSummary.importable}</Descriptions.Item>
              <Descriptions.Item label="跳过">{importSummary.skipped}</Descriptions.Item>
            </Descriptions>

            {importSummary.unbound > 0 ? (
              <Alert
                type="error"
                showIcon
                message={`仍有 ${importSummary.unbound} 条未绑定规则节点`}
                description="未绑定用例不能导入，请返回上一步手动绑定或勾选跳过导入。"
              />
            ) : (
              <Alert
                type="success"
                showIcon
                message="校验通过，可执行导入"
                description="确认后将批量创建测试用例并建立规则节点/路径绑定关系。"
              />
            )}

            <Table<ImportPreviewRow>
              rowKey="index"
              size="small"
              pagination={{ pageSize: 6 }}
              dataSource={importRows}
              columns={[
                { title: "标题", dataIndex: "title", render: (value: string) => renderEllipsisCell(value, 220) },
                {
                  title: "绑定节点数",
                  render: (_, row) => row.bound_rule_node_ids.length,
                },
                {
                  title: "风险等级",
                  dataIndex: "risk_level",
                  render: (value: RiskLevel) => <Tag color={getRiskTagColor(value)}>{getRiskLevelLabel(value)}</Tag>,
                },
                {
                  title: "状态",
                  render: (_, row) => (row.skip_import ? <Tag>跳过</Tag> : <Tag color="green">导入</Tag>),
                },
              ]}
            />
          </Space>
        ) : null}
      </Modal>

      <Modal
        open={!!editingCase}
        title="修改用例"
        okText="保存"
        confirmLoading={editSubmitting}
        onOk={submitEdit}
        onCancel={closeEdit}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="title" label="用例标题" rules={[{ required: true, message: "请输入标题" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="precondition" label="前置条件">
            <Input.TextArea rows={3} placeholder="如：存在一个客户，客户类型=代理商" />
          </Form.Item>
          <Form.Item name="steps" label="执行步骤" rules={[{ required: true, message: "请输入步骤" }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="expected_result" label="预期结果" rules={[{ required: true, message: "请输入预期结果" }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="risk_level" label="风险等级" rules={[{ required: true }]}>
            <Select options={riskOptions} />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}>
            <Select options={statusOptions} />
          </Form.Item>
          <Form.Item
            name="bound_rule_node_ids"
            label="绑定规则节点"
            rules={[{ required: true, message: "至少选择一个规则节点" }]}
          >
            <Select mode="multiple" options={nodeOptions} />
          </Form.Item>
          <Form.Item
            name="bound_path_ids"
            label="绑定规则路径"
            dependencies={["bound_rule_node_ids"]}
            rules={[
              {
                validator: async (_, value: string[] = []) => {
                  if (!value.length) {
                    return;
                  }
                  const hasInvalid = value.some((pathId) => !matchedEditPathIdSet.has(pathId));
                  if (hasInvalid) {
                    throw new Error("所选规则路径需包含已选择的全部规则节点");
                  }
                },
              },
            ]}
          >
            <Select mode="multiple" options={editPathOptions} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={!!viewingCase}
        title="用例详情"
        width={920}
        className="test-case-detail-modal"
        footer={null}
        onCancel={() => setViewingCase(null)}
        destroyOnClose
      >
        <Descriptions bordered column={1} size="small">
          <Descriptions.Item label="ID">{viewingCase?.id}</Descriptions.Item>
          <Descriptions.Item label="标题">{viewingCase?.title}</Descriptions.Item>
          <Descriptions.Item label="风险">
            <Tag color={getRiskTagColor(viewingCase?.risk_level)}>{getRiskLevelLabel(viewingCase?.risk_level)}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="状态">{getTestCaseStatusLabel(viewingCase?.status)}</Descriptions.Item>
          <Descriptions.Item label="前置条件">
            <div style={{ whiteSpace: "pre-wrap" }}>{viewingCase?.precondition || "-"}</div>
          </Descriptions.Item>
          <Descriptions.Item label="执行步骤">{viewingCase?.steps || "-"}</Descriptions.Item>
          <Descriptions.Item label="预期结果">{viewingCase?.expected_result || "-"}</Descriptions.Item>
          <Descriptions.Item label="绑定节点">
            {viewingCase?.bound_rule_node_ids?.length ? (
              <Space wrap className="detail-chip-list">
                {viewingCase.bound_rule_node_ids.map((nodeId) => (
                  <Tag key={nodeId}>{getNodeDisplay(nodeId)}</Tag>
                ))}
              </Space>
            ) : (
              "-"
            )}
          </Descriptions.Item>
          <Descriptions.Item label="绑定路径">
            {viewingCase?.bound_path_ids?.length ? (
              <Space direction="vertical" size={4} className="detail-chip-list" style={{ width: "100%" }}>
                {viewingCase.bound_path_ids.map((pathId) => (
                  <Tag key={pathId}>{getPathDisplay(pathId)}</Tag>
                ))}
              </Space>
            ) : (
              "-"
            )}
          </Descriptions.Item>
        </Descriptions>
      </Modal>

      <Space direction="vertical" style={{ width: "100%", marginTop: 16 }}>
        <Alert
          type="warning"
          showIcon
          message="变更影响分析提示"
          description="当规则节点更新后，后端会把关联用例自动标记为待复核，用例列表可直接看到风险。"
        />
      </Space>
    </div>
  );
}
