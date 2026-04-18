import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Collapse,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ScanOutlined,
} from "@ant-design/icons";
import { getErrorMessage } from "../../api/client";
import type {
  AnalysisStage,
  EffectiveSnapshot,
  PredevAnalysisResponse,
  RequirementInput,
  ReviewSnapshotResponse,
  RiskAnalysisTask,
  RiskAnalysisTaskSummary,
  RiskDecisionType,
  RiskItem,
  RiskValidity,
} from "../../types";
import { analyzeRisks, clarifyRisk, decideRisk, deleteRisk, fetchRisks } from "../../api/risks";
import {
  addRequirementInput,
  getLatestSnapshot,
  listRequirementInputs,
} from "../../api/effectiveRequirements";
import { fetchRiskAnalysisTask, fetchRiskAnalysisTaskSummary, startUnifiedRiskAnalysis } from "../../api/riskAnalysisTasks";
import { fetchProductDocs, suggestDocUpdate } from "../../api/productDocs";
import { useAppStore } from "../../stores/appStore";
import { getRequirementInputTypeLabel, getRiskAnalysisTaskStatusLabel } from "../../utils/enumLabels";
import TaskProgressBar, { type TaskStatus } from "../../components/TaskProgressBar";
import { trackEvent } from "../../utils/telemetry";

const riskLevelColors: Record<string, string> = {
  critical: "#ff4d4f",
  high: "#fa8c16",
  medium: "#fadb14",
  low: "#52c41a",
};

const riskLevelLabels: Record<string, string> = {
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
};

const decisionIcons: Record<RiskDecisionType, React.ReactNode> = {
  pending: <ExclamationCircleOutlined style={{ color: "#faad14" }} />,
  accepted: <CheckCircleOutlined style={{ color: "#52c41a" }} />,
  ignored: <CloseCircleOutlined style={{ color: "#d9d9d9" }} />,
};

const stageLabels: Record<string, string> = {
  review: "评审",
  pre_dev: "开发前",
  pre_release: "提测前",
};

const validityLabels: Record<RiskValidity, string> = {
  active: "有效",
  superseded: "已过时",
  reopened: "重新打开",
  resolved: "已解决",
};

const validityTagColors: Record<RiskValidity, string> = {
  active: "green",
  superseded: "default",
  reopened: "orange",
  resolved: "blue",
};

const snapshotFieldLabels: Record<string, string> = {
  goal: "需求目标",
  main_flow: "主流程",
  preconditions: "前置条件",
  state_changes: "状态变更",
  exceptions: "异常流程",
  constraints: "约束条件",
  performance: "性能要求",
  compatibility: "兼容性要求",
  integration: "集成/联动要求",
  other: "其他",
};

const derivationLabels: Record<string, string> = {
  explicit: "明确给出",
  inferred: "推断得到",
  missing: "缺失待补充",
  contradicted: "存在矛盾",
};

const requirementInputTypeOptions = [
  { label: getRequirementInputTypeLabel("raw_requirement"), value: "raw_requirement" },
  { label: getRequirementInputTypeLabel("pm_addendum"), value: "pm_addendum" },
  { label: getRequirementInputTypeLabel("test_clarification"), value: "test_clarification" },
  { label: getRequirementInputTypeLabel("review_note"), value: "review_note" },
];

const STAGE_ORDER: AnalysisStage[] = ["review", "pre_dev", "pre_release"];

const EMPTY_TASK_SUMMARY: RiskAnalysisTaskSummary = {
  review: null,
  pre_dev: null,
  pre_release: null,
};

function isRiskAnalysisTaskInProgress(task?: RiskAnalysisTask | null): boolean {
  return task?.status === "queued" || task?.status === "running";
}

function parseRiskAnalysisTaskResult<T>(task?: RiskAnalysisTask | null): T | null {
  if (!task?.result_json) return null;
  try {
    return JSON.parse(task.result_json) as T;
  } catch {
    return null;
  }
}

type RiskPanelProps = {
  requirementId: number | null;
  onNodeLocate?: (nodeId: string) => void;
  onRiskConverted?: () => void;
  onRisksChange?: (risks: RiskItem[]) => void;
};

export default function RiskPanel({ requirementId, onNodeLocate, onRiskConverted, onRisksChange }: RiskPanelProps) {
  const { selectedProjectId, projects } = useAppStore();
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [riskSummary, setRiskSummary] = useState({
    total: 0,
    pending: 0,
    accepted: 0,
    ignored: 0,
    active: 0,
    superseded: 0,
    reopened: 0,
    resolved: 0,
  });
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [autoCreateNode, setAutoCreateNode] = useState(true);
  const [unifiedLoading, setUnifiedLoading] = useState(false);
  const [latestSnapshot, setLatestSnapshot] = useState<EffectiveSnapshot | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [requirementInputs, setRequirementInputs] = useState<RequirementInput[]>([]);
  const [inputsLoading, setInputsLoading] = useState(false);
  const [validityFilter, setValidityFilter] = useState<RiskValidity | "all">("all");
  const [reviewResult, setReviewResult] = useState<ReviewSnapshotResponse | null>(null);
  const [predevResult, setPredevResult] = useState<PredevAnalysisResponse | null>(null);
  const [stageTasks, setStageTasks] = useState<RiskAnalysisTaskSummary>(EMPTY_TASK_SUMMARY);
  const [activeStage, setActiveStage] = useState<AnalysisStage | null>(null);

  const [decisionModal, setDecisionModal] = useState<{
    risk: RiskItem;
    type: "accepted" | "ignored";
  } | null>(null);
  const [form] = Form.useForm();

  const [clarifyModal, setClarifyModal] = useState<RiskItem | null>(null);
  const [clarifyForm] = Form.useForm();
  const [inputForm] = Form.useForm();
  const stagePollTimerRef = useRef<number | null>(null);
  const stagePollDelayRef = useRef(2000);
  const previousTaskStatusRef = useRef<Record<AnalysisStage, string | null>>({
    review: null,
    pre_dev: null,
    pre_release: null,
  });

  const loadRisks = useCallback(async () => {
    if (!requirementId) {
      setRisks([]);
      setRiskSummary({
        total: 0,
        pending: 0,
        accepted: 0,
        ignored: 0,
        active: 0,
        superseded: 0,
        reopened: 0,
        resolved: 0,
      });
      return [];
    }
    setLoading(true);
    try {
      const resp = await fetchRisks(requirementId);
      setRisks(resp.risks);
      setRiskSummary({
        total: resp.total,
        pending: resp.pending,
        accepted: resp.accepted,
        ignored: resp.ignored,
        active: resp.active,
        superseded: resp.superseded,
        reopened: resp.reopened,
        resolved: resp.resolved,
      });
      return resp.risks;
    } catch {
      message.error("加载风险项失败");
      return [];
    } finally {
      setLoading(false);
    }
  }, [requirementId]);

  const loadLatestSnapshot = useCallback(async () => {
    if (!requirementId) {
      setLatestSnapshot(null);
      return null;
    }
    setSnapshotLoading(true);
    try {
      const snapshot = await getLatestSnapshot(requirementId);
      setLatestSnapshot(snapshot);
      return snapshot;
    } catch {
      message.error("加载最新快照失败");
      return null;
    } finally {
      setSnapshotLoading(false);
    }
  }, [requirementId]);

  const loadRequirementInputs = useCallback(async () => {
    if (!requirementId) {
      setRequirementInputs([]);
      return [];
    }
    setInputsLoading(true);
    try {
      const items = await listRequirementInputs(requirementId);
      setRequirementInputs(items);
      return items;
    } catch {
      message.error("加载需求输入失败");
      return [];
    } finally {
      setInputsLoading(false);
    }
  }, [requirementId]);

  const hydrateStageTaskResult = useCallback((stage: AnalysisStage, task: RiskAnalysisTask | null) => {
    if (!task?.result_json) return;

    if (stage === "review") {
      const parsed = parseRiskAnalysisTaskResult<ReviewSnapshotResponse>(task);
      if (!parsed) return;
      setReviewResult(parsed);
      if (parsed.snapshot) setLatestSnapshot(parsed.snapshot);
      return;
    }

    if (stage === "pre_dev") {
      const parsed = parseRiskAnalysisTaskResult<PredevAnalysisResponse>(task);
      if (!parsed) return;
      setPredevResult(parsed);
      if (parsed.snapshot) setLatestSnapshot(parsed.snapshot);
    }
  }, []);

  const getPreferredActiveStage = useCallback(
    (summary: RiskAnalysisTaskSummary, preferred: AnalysisStage | null) => {
      if (preferred && isRiskAnalysisTaskInProgress(summary[preferred])) {
        return preferred;
      }
      for (const stage of STAGE_ORDER) {
        if (isRiskAnalysisTaskInProgress(summary[stage])) {
          return stage;
        }
      }
      return preferred;
    },
    [],
  );

  const loadTaskSummary = useCallback(async () => {
    if (!requirementId) {
      setStageTasks(EMPTY_TASK_SUMMARY);
      setActiveStage(null);
      return EMPTY_TASK_SUMMARY;
    }
    try {
      const summary = await fetchRiskAnalysisTaskSummary(requirementId);
      setStageTasks(summary);
      STAGE_ORDER.forEach((stage) => hydrateStageTaskResult(stage, summary[stage]));
      setActiveStage((prev) => getPreferredActiveStage(summary, prev));
      return summary;
    } catch (error) {
      message.error(getErrorMessage(error, "加载阶段任务失败"));
      return EMPTY_TASK_SUMMARY;
    }
  }, [getPreferredActiveStage, hydrateStageTaskResult, requirementId]);

  const refreshStageTask = useCallback(
    async (stage: AnalysisStage) => {
      if (!requirementId) return null;
      const task = await fetchRiskAnalysisTask(requirementId, stage);
      setStageTasks((prev) => ({ ...prev, [stage]: task }));
      hydrateStageTaskResult(stage, task);
      return task;
    },
    [hydrateStageTaskResult, requirementId],
  );

  useEffect(() => {
    loadRisks();
  }, [loadRisks]);

  useEffect(() => {
    void loadLatestSnapshot();
    void loadRequirementInputs();
    void loadTaskSummary();
    setReviewResult(null);
    setPredevResult(null);
    setStageTasks(EMPTY_TASK_SUMMARY);
    setActiveStage(null);
    stagePollDelayRef.current = 2000;
    previousTaskStatusRef.current = {
      review: null,
      pre_dev: null,
      pre_release: null,
    };
    setValidityFilter("all");
  }, [loadLatestSnapshot, loadRequirementInputs, loadTaskSummary]);

  const filteredRisks = useMemo(() => {
    return risks.filter((risk) => {
      const validityMatches = validityFilter === "all" || (risk.validity || "active") === validityFilter;
      return validityMatches;
    });
  }, [risks, validityFilter]);

  const stageGroupedRisks = useMemo(() => {
    const groups: Record<string, RiskItem[]> = {
      review: [],
      pre_dev: [],
      pre_release: [],
      other: [],
    };
    for (const risk of filteredRisks) {
      const stage = (risk.analysis_stage || "") as string;
      if (stage === "review" || stage === "pre_dev" || stage === "pre_release") {
        groups[stage].push(risk);
      } else {
        groups.other.push(risk);
      }
    }
    return groups;
  }, [filteredRisks]);

  const anyTaskInProgress = useMemo(() => {
    return STAGE_ORDER.some((stage) => isRiskAnalysisTaskInProgress(stageTasks[stage]));
  }, [stageTasks]);

  const latestSnapshotStale = latestSnapshot?.is_stale === true;

  const handleAnalyze = async () => {
    if (!requirementId) return;
    setAnalyzing(true);
    try {
      await analyzeRisks(requirementId);
      message.success("风险分析完成");
      const newRisks = await loadRisks();
      onRisksChange?.(newRisks);
    } catch {
      message.error("风险分析失败");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleUnifiedAnalysis = async () => {
    if (!requirementId) return;
    setUnifiedLoading(true);
    trackEvent("risk.analysis.start", { requirement_id: requirementId });
    try {
      const result = await startUnifiedRiskAnalysis(requirementId);
      await loadTaskSummary();
      const stageCount = result.stages.length;
      message.success(`已开始风险分析（${stageCount} 个阶段）`);
      trackEvent("risk.analysis.complete", { requirement_id: requirementId, stage_count: stageCount });
    } catch (error) {
      message.error(getErrorMessage(error, "启动风险分析失败"));
      trackEvent("risk.analysis.failure", {
        requirement_id: requirementId,
        message: getErrorMessage(error, ""),
      });
    } finally {
      setUnifiedLoading(false);
    }
  };

  useEffect(() => {
    setActiveStage((prev) => getPreferredActiveStage(stageTasks, prev));
  }, [getPreferredActiveStage, stageTasks]);

  useEffect(() => {
    if (stagePollTimerRef.current) {
      window.clearTimeout(stagePollTimerRef.current);
      stagePollTimerRef.current = null;
    }
    if (!requirementId || !activeStage) {
      stagePollDelayRef.current = 2000;
      return;
    }

    const task = stageTasks[activeStage];
    if (!isRiskAnalysisTaskInProgress(task)) {
      stagePollDelayRef.current = 2000;
      return;
    }

    const delay = stagePollDelayRef.current;
    stagePollTimerRef.current = window.setTimeout(() => {
      refreshStageTask(activeStage)
        .then((nextTask) => {
          if (nextTask && isRiskAnalysisTaskInProgress(nextTask)) {
            stagePollDelayRef.current = Math.min(stagePollDelayRef.current + 1000, 5000);
            return;
          }
          stagePollDelayRef.current = 2000;
        })
        .catch((error) => {
          stagePollDelayRef.current = Math.min(stagePollDelayRef.current + 1000, 5000);
          message.error(getErrorMessage(error, "刷新阶段任务失败"));
        });
    }, delay);

    return () => {
      if (stagePollTimerRef.current) {
        window.clearTimeout(stagePollTimerRef.current);
        stagePollTimerRef.current = null;
      }
    };
  }, [activeStage, refreshStageTask, requirementId, stageTasks]);

  useEffect(() => {
    STAGE_ORDER.forEach((stage) => {
      const nextStatus = stageTasks[stage]?.status || null;
      const prevStatus = previousTaskStatusRef.current[stage];
      previousTaskStatusRef.current[stage] = nextStatus;

      if (!prevStatus || prevStatus === nextStatus) {
        return;
      }

      const task = stageTasks[stage];
      if (nextStatus === "completed") {
        message.success(
          stage === "review"
            ? "评审分析完成"
            : "开发前分析完成",
        );
        void (async () => {
          const newRisks = await loadRisks();
          onRisksChange?.(newRisks);
          await loadRequirementInputs();
          await loadLatestSnapshot();
        })();
        return;
      }

      if (nextStatus === "failed") {
        message.error(task?.last_error || "阶段任务执行失败");
        return;
      }

      if (nextStatus === "interrupted") {
        message.warning(task?.last_error || "阶段任务已中断");
      }
    });
  }, [loadLatestSnapshot, loadRequirementInputs, loadRisks, onRisksChange, stageTasks]);

  const handleAddRequirementInput = async () => {
    if (!requirementId) return;
    const values = await inputForm.validateFields();
    try {
      await addRequirementInput(requirementId, {
        input_type: values.input_type,
        content: values.content,
      });
      message.success("需求输入已添加");
      inputForm.resetFields();
      await loadRequirementInputs();
    } catch {
      message.error("添加需求输入失败");
    }
  };

  const openDecisionModal = (risk: RiskItem, type: "accepted" | "ignored") => {
    setDecisionModal({ risk, type });
    form.resetFields();
  };

  const handleDecision = async () => {
    if (!decisionModal) return;
    const values = await form.validateFields();
    try {
      await decideRisk(
        decisionModal.risk.id,
        decisionModal.type,
        values.reason,
        autoCreateNode,
      );
      message.success(decisionModal.type === "accepted" ? "已接受" : "已忽略");
      setDecisionModal(null);
      const newRisks = await loadRisks();
      onRisksChange?.(newRisks);
      if (decisionModal.type === "accepted" && autoCreateNode) {
        onRiskConverted?.();
      }
    } catch {
      message.error("操作失败");
    }
  };

  const handleClarify = async () => {
    if (!clarifyModal) return;
    const values = await clarifyForm.validateFields();
    try {
      await clarifyRisk(
        clarifyModal.id,
        values.clarification_text,
        values.doc_update_needed ?? false,
      );
      message.success("澄清已保存");

      if (values.doc_update_needed) {
        try {
          const project = projects.find((p) => p.id === selectedProjectId);
          const productCode = project?.product_code;
          if (!productCode) {
            message.warning("当前项目未关联产品文档，无法自动生成更新建议");
          } else {
            const docs = await fetchProductDocs();
            const doc = docs.find((d) => d.product_code === productCode);
            if (!doc) {
              message.warning("未找到匹配的产品文档，无法自动生成更新建议");
            } else {
              await suggestDocUpdate({
                product_doc_id: doc.id,
                risk_item_id: clarifyModal.id,
                clarification_text: values.clarification_text,
              });
              message.success("文档更新建议已生成");
            }
          }
        } catch {
          message.error("生成文档更新建议失败，但澄清已保存");
        }
      }

      setClarifyModal(null);
      const newRisks = await loadRisks();
      onRisksChange?.(newRisks);
      await loadRequirementInputs();
    } catch {
      message.error("澄清保存失败");
    }
  };

  const handleDelete = async (riskId: string) => {
    try {
      await deleteRisk(riskId);
      message.success("已删除");
      const newRisks = await loadRisks();
      onRisksChange?.(newRisks);
    } catch {
      message.error("删除失败");
    }
  };

  const renderRiskCard = (risk: RiskItem) => (
    <div
      key={risk.id}
      style={{
        padding: "10px 12px",
        borderRadius: 8,
        border: "1px solid #f0f0f0",
        background: risk.decision === "pending" ? "#fffbe6" : "#fafafa",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        {decisionIcons[risk.decision]}
        <Tag
          color={riskLevelColors[risk.risk_level]}
          style={{ color: risk.risk_level === "medium" ? "#666" : "#fff" }}
        >
          {riskLevelLabels[risk.risk_level] || risk.risk_level}
        </Tag>
        {risk.decision !== "pending" && (
          <Tag>{risk.decision === "accepted" ? "已接受" : "已忽略"}</Tag>
        )}
        <Tag color={validityTagColors[risk.validity || "active"]}>
          {validityLabels[risk.validity || "active"]}
        </Tag>
        {risk.analysis_stage && <Tag>{stageLabels[risk.analysis_stage]}</Tag>}
      </div>
      <Typography.Paragraph
        style={{ margin: 0, fontSize: 13 }}
        ellipsis={{ rows: 3, expandable: true }}
      >
        {risk.description}
      </Typography.Paragraph>
      <Typography.Paragraph
        type="secondary"
        style={{ margin: "4px 0 0", fontSize: 12 }}
        ellipsis={{ rows: 2, expandable: true }}
      >
        建议：{risk.suggestion}
      </Typography.Paragraph>
      {risk.clarification_text && (
        <Typography.Paragraph
          style={{ margin: "4px 0 0", fontSize: 12, color: "#1890ff" }}
        >
          澄清：{risk.clarification_text}
          {risk.doc_update_needed && <Tag color="warning" style={{ marginLeft: 4 }}>需更新文档</Tag>}
        </Typography.Paragraph>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
        {risk.related_node_id && (
          <Tooltip title="定位到关联节点">
            <Button
              size="small"
              type="link"
              onClick={() => onNodeLocate?.(risk.related_node_id!)}
            >
              定位节点
            </Button>
          </Tooltip>
        )}
        {risk.decision === "pending" && (
          <>
            <Button size="small" type="primary" onClick={() => openDecisionModal(risk, "accepted")}>
              接受
            </Button>
            <Button size="small" onClick={() => openDecisionModal(risk, "ignored")}>
              忽略
            </Button>
          </>
        )}
        {risk.decision === "accepted" && (
          <Button
            size="small"
            type="dashed"
            onClick={() => {
              setClarifyModal(risk);
              clarifyForm.setFieldsValue({
                clarification_text: risk.clarification_text || "",
                doc_update_needed: risk.doc_update_needed || false,
              });
            }}
          >
            澄清
          </Button>
        )}
        <Popconfirm
          title="确定删除该风险项吗？"
          onConfirm={() => handleDelete(risk.id)}
          okText="确定"
          cancelText="取消"
        >
          <Button size="small" danger>
            删除
          </Button>
        </Popconfirm>
      </div>
      {risk.decision_reason && (
        <Typography.Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: "block" }}>
          理由：{risk.decision_reason}
        </Typography.Text>
      )}
    </div>
  );

  const latestSnapshotFields = (latestSnapshot?.fields || []).filter(
    (field) => field.field_key !== "rollout_strategy",
  );
  const stageNotice = reviewResult?.clarification_hints?.length
    ? "评审分析已生成澄清提示"
    : predevResult?.conflicts?.length
      ? "开发前分析发现冲突项"
      : null;
  const stageTaskAlerts = STAGE_ORDER.map((stage) => {
    const task = stageTasks[stage];
    if (!task) return null;

    const retainedResultHint =
      isRiskAnalysisTaskInProgress(task) && task.result_json ? "后台重新分析中，当前仍展示上次结果。" : null;

    let progressStatus: TaskStatus = "idle";
    if (task.status === "completed") progressStatus = "success";
    else if (task.status === "interrupted") progressStatus = "idle";
    else if (task.status === "failed") progressStatus = "error";
    else if (isRiskAnalysisTaskInProgress(task)) progressStatus = "running";

    const descParts: string[] = [];
    if (task.progress_message) descParts.push(task.progress_message);
    if (retainedResultHint) descParts.push(retainedResultHint);
    if (task.last_error && task.status !== "completed") descParts.push(task.last_error);
    const desc = descParts.join(" · ");

    return (
      <TaskProgressBar
        key={stage}
        compact={progressStatus !== "running"}
        title={`${stageLabels[stage]}：${getRiskAnalysisTaskStatusLabel(task.status)}`}
        description={desc}
        percent={task.progress_percent ?? undefined}
        indeterminate={task.progress_percent == null}
        status={progressStatus}
      />
    );
  }).filter(Boolean);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minHeight: 0,
        overflow: "hidden",
      }}
    >
      <div style={{ padding: "10px 12px", borderBottom: "1px solid #f0f0f0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <Typography.Text strong>风险分析</Typography.Text>
          <Button
            size="small"
            type="primary"
            icon={<ScanOutlined />}
            onClick={() => void handleUnifiedAnalysis()}
            loading={unifiedLoading}
            disabled={!requirementId || anyTaskInProgress}
          >
            开始分析
          </Button>
        </div>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 8, padding: "6px 10px" }}
          message="风险识别仅供参考，不会拦截后续流程。"
          description={
            <Space direction="vertical" size={2} style={{ width: "100%" }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                本次分析基于需求正文 + 追问结论，规则树节点不参与本次分析。
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                处理完风险后，可直接继续生成规则树和测试用例。
              </Typography.Text>
            </Space>
          }
        />
        <Space size={12} wrap>
          <span>
            可见 <strong>{filteredRisks.length}</strong>
          </span>
          <span>
            <Badge status="warning" />待处理 <strong>{riskSummary.pending}</strong>
          </span>
          <span>
            <Badge status="success" />已接受 <strong>{riskSummary.accepted}</strong>
          </span>
          <span>
            <Badge status="default" />已忽略 <strong>{riskSummary.ignored}</strong>
          </span>
        </Space>
        {latestSnapshotStale && (
          <Typography.Text type="warning" style={{ display: "block", marginTop: 8, fontSize: 12 }}>
            当前最新快照已过期，分析会基于最新输入重新生成。
          </Typography.Text>
        )}
        {stageTaskAlerts.length > 0 && (
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
            {stageTaskAlerts}
          </div>
        )}
        <Collapse
          ghost
          size="small"
          items={[
            {
              key: "advanced",
              label: <Typography.Text type="secondary" style={{ fontSize: 12 }}>更多筛选与配置</Typography.Text>,
              children: (
                <Space direction="vertical" size={8} style={{ width: "100%" }}>
                  <Space size={12} wrap>
                    <span><Badge color="green" />有效 <strong>{riskSummary.active}</strong></span>
                    <span><Badge color="#bfbfbf" />已过时 <strong>{riskSummary.superseded}</strong></span>
                    <span><Badge color="orange" />重开 <strong>{riskSummary.reopened}</strong></span>
                    <span><Badge color="blue" />已解决 <strong>{riskSummary.resolved}</strong></span>
                  </Space>
                  <Space wrap>
                    <Select
                      size="small"
                      style={{ width: 130 }}
                      value={validityFilter}
                      onChange={(value) => setValidityFilter(value)}
                      options={[
                        { label: "全部有效性", value: "all" },
                        { label: "有效", value: "active" },
                        { label: "已过时", value: "superseded" },
                        { label: "重新打开", value: "reopened" },
                        { label: "已解决", value: "resolved" },
                      ]}
                    />
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <Switch size="small" checked={autoCreateNode} onChange={setAutoCreateNode} />
                      <Tooltip title="开启后，接受风险时自动在规则树上创建对应的异常节点">
                        <Typography.Text type="secondary" style={{ fontSize: 12, cursor: "help" }}>
                          接受时自动创建节点
                        </Typography.Text>
                      </Tooltip>
                    </div>
                  </Space>
                  {latestSnapshot && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      最新快照：{latestSnapshot.summary || "未生成摘要"}
                    </Typography.Text>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </div>

      <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, overflow: "auto", padding: "8px 0" }}>
          <div style={{ padding: "0 16px 8px", display: "flex", flexDirection: "column", gap: 8 }}>
            {stageNotice && <Alert type="info" showIcon message={stageNotice} />}
            {latestSnapshotStale && (
              <Alert
                type="warning"
                showIcon
                message="需求已变更，当前快照不是基于最新输入生成，结果可能不可靠，请重新执行评审分析。"
              />
            )}
            <Collapse
              ghost
              items={[
                {
                  key: "snapshot",
                  label: "最新有效需求快照",
                  children: snapshotLoading ? (
                    <Spin size="small" />
                  ) : latestSnapshot ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <Typography.Text type="secondary">
                        阶段：{stageLabels[latestSnapshot.stage]}，字段数：{latestSnapshotFields.length}
                      </Typography.Text>
                      {latestSnapshotFields.length === 0 ? (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无快照字段" />
                      ) : (
                        latestSnapshotFields.map((field) => (
                          <div key={field.id} style={{ border: "1px solid #f0f0f0", borderRadius: 8, padding: 10 }}>
                            <Space wrap>
                              <Tag>{snapshotFieldLabels[field.field_key] || field.field_key}</Tag>
                              {field.derivation && (
                                <Tag color="blue">{derivationLabels[field.derivation] || field.derivation}</Tag>
                              )}
                              {field.confidence != null && <Tag color="gold">置信度 {field.confidence}</Tag>}
                            </Space>
                            <Typography.Paragraph style={{ margin: "8px 0 0", whiteSpace: "pre-wrap" }}>
                              {field.value || "-"}
                            </Typography.Paragraph>
                            {field.source_refs && (
                              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                来源：{field.source_refs}
                              </Typography.Text>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无有效需求快照" />
                  ),
                },
                {
                  key: "inputs",
                  label: "正式需求输入",
                  children: (
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                      <Form layout="vertical" form={inputForm}>
                        <Form.Item
                          name="input_type"
                          label="输入类型"
                          rules={[{ required: true, message: "请选择输入类型" }]}
                        >
                          <Select options={requirementInputTypeOptions} placeholder="选择输入类型" />
                        </Form.Item>
                        <Form.Item
                          name="content"
                          label="输入内容"
                          rules={[{ required: true, message: "请输入输入内容" }]}
                        >
                          <Input.TextArea rows={3} placeholder="输入 PM 补充、测试澄清或评审备注" />
                        </Form.Item>
                        <Button size="small" type="primary" onClick={() => void handleAddRequirementInput()} disabled={!requirementId}>
                          添加输入
                        </Button>
                      </Form>
                      {inputsLoading ? (
                        <Spin size="small" />
                      ) : requirementInputs.length === 0 ? (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无正式输入" />
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                          {requirementInputs.map((item) => (
                            <div key={item.id} style={{ border: "1px solid #f0f0f0", borderRadius: 8, padding: 10 }}>
                              <Space wrap>
                                <Tag>{getRequirementInputTypeLabel(item.input_type)}</Tag>
                                {item.created_at && <Typography.Text type="secondary">{item.created_at}</Typography.Text>}
                              </Space>
                              <Typography.Paragraph style={{ margin: "8px 0 0", whiteSpace: "pre-wrap" }}>
                                {item.content}
                              </Typography.Paragraph>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ),
                },
              ]}
            />
          </div>
          {loading ? (
            <div style={{ textAlign: "center", padding: 32 }}>
              <Spin />
            </div>
          ) : filteredRisks.length === 0 ? (
            <div style={{ padding: "16px 16px 24px" }}>
              <Alert
                type="success"
                showIcon
                message="当前没有待处理或历史风险"
                description="完成澄清后，系统不会拦截你的流程。可继续去「规则树」补全节点或生成用例，这里会持续收集所有 AI 识别到的风险项，供有需要时复盘。"
              />
            </div>
          ) : (
            <div style={{ padding: "0 16px", display: "flex", flexDirection: "column", gap: 14 }}>
              {(["review", "pre_dev", "pre_release", "other"] as const).map((stage) => {
                const items = stageGroupedRisks[stage];
                if (items.length === 0) return null;
                const label =
                  stage === "other"
                    ? "未归类阶段"
                    : `${stageLabels[stage] || stage}阶段 · ${items.length} 条`;
                return (
                  <div key={stage}>
                    <Typography.Text strong style={{ fontSize: 12, color: "#6b7a90" }}>
                      {label}
                    </Typography.Text>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 6 }}>
                      {items.map(renderRiskCard)}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <Modal
        title={decisionModal?.type === "accepted" ? "接受风险" : "忽略风险"}
        open={!!decisionModal}
        onCancel={() => setDecisionModal(null)}
        onOk={handleDecision}
        okText="确认"
      >
        <Form layout="vertical" form={form}>
          <Form.Item name="reason" label="决策理由" rules={[{ required: true, message: "请填写理由" }]}>
            <Input.TextArea rows={3} placeholder="请说明原因" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="产品澄清"
        open={!!clarifyModal}
        onCancel={() => setClarifyModal(null)}
        onOk={handleClarify}
        okText="保存澄清"
      >
        <Form layout="vertical" form={clarifyForm}>
          <Form.Item
            name="clarification_text"
            label="澄清说明"
            rules={[{ required: true, message: "请填写澄清说明" }]}
          >
            <Input.TextArea rows={4} placeholder="请说明该风险的澄清情况" />
          </Form.Item>
          <Form.Item name="doc_update_needed" valuePropName="checked">
            <Checkbox>需要更新产品文档</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
