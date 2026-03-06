import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
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
import type { RiskCategory, RiskDecisionType, RiskItem } from "../../types";
import { analyzeRisks, decideRisk, deleteRisk, fetchRisks } from "../../api/risks";

const categoryLabels: Record<RiskCategory, string> = {
  input_validation: "输入校验",
  flow_gap: "流程缺口",
  data_integrity: "数据完整性",
  boundary: "边界条件",
  security: "安全风险",
};

const categoryColors: Record<RiskCategory, string> = {
  input_validation: "orange",
  flow_gap: "red",
  data_integrity: "purple",
  boundary: "blue",
  security: "volcano",
};

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

type RiskPanelProps = {
  requirementId: number | null;
  onNodeLocate?: (nodeId: string) => void;
  onRiskConverted?: () => void;
  onRisksChange?: (risks: RiskItem[]) => void;
};

export default function RiskPanel({ requirementId, onNodeLocate, onRiskConverted, onRisksChange }: RiskPanelProps) {
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);

  const [decisionModal, setDecisionModal] = useState<{
    risk: RiskItem;
    type: "accepted" | "ignored";
  } | null>(null);
  const [form] = Form.useForm();

  const loadRisks = useCallback(async () => {
    if (!requirementId) {
      setRisks([]);
      return [];
    }
    setLoading(true);
    try {
      const resp = await fetchRisks(requirementId);
      setRisks(resp.risks);
      return resp.risks;
    } catch {
      message.error("加载风险项失败");
      return [];
    } finally {
      setLoading(false);
    }
  }, [requirementId]);

  useEffect(() => {
    loadRisks();
  }, [loadRisks]);

  const stats = useMemo(() => {
    const pending = risks.filter((r) => r.decision === "pending").length;
    const accepted = risks.filter((r) => r.decision === "accepted").length;
    const ignored = risks.filter((r) => r.decision === "ignored").length;
    return { pending, accepted, ignored, total: risks.length };
  }, [risks]);

  const groupedRisks = useMemo(() => {
    const groups: Record<string, RiskItem[]> = {};
    for (const risk of risks) {
      const cat = risk.category;
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(risk);
    }
    return groups;
  }, [risks]);

  const [activeKeys, setActiveKeys] = useState<string[]>([]);

  useEffect(() => {
    setActiveKeys(Object.keys(groupedRisks));
  }, [groupedRisks]);

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
        values.auto_create_node ?? false,
      );
      message.success(decisionModal.type === "accepted" ? "已接受" : "已忽略");
      setDecisionModal(null);
      const newRisks = await loadRisks();
      onRisksChange?.(newRisks);
      if (decisionModal.type === "accepted" && values.auto_create_node) {
        onRiskConverted?.();
      }
    } catch {
      message.error("操作失败");
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

  const collapseItems = Object.entries(groupedRisks).map(([category, items]) => ({
    key: category,
    label: (
      <Space>
        <Tag color={categoryColors[category as RiskCategory]}>
          {categoryLabels[category as RiskCategory] || category}
        </Tag>
        <Badge count={items.length} style={{ backgroundColor: "#8c8c8c" }} />
      </Space>
    ),
    children: (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {items.map((risk) => (
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
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
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
        ))}
      </div>
    ),
  }));

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
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <Typography.Text strong>风险识别</Typography.Text>
          <Tooltip title={stats.pending > 0 ? "请先处理所有待处理风险项" : undefined}>
            <span>
              <Button
                size="small"
                type="primary"
                icon={<ScanOutlined />}
                loading={analyzing}
                onClick={handleAnalyze}
                disabled={!requirementId || stats.pending > 0}
              >
                分析
              </Button>
            </span>
          </Tooltip>
        </div>
        <Space size={12} wrap>
          <span>
            <Badge status="warning" />
            待处理 <strong>{stats.pending}</strong>
          </span>
          <span>
            <Badge status="success" />
            已接受 <strong>{stats.accepted}</strong>
          </span>
          <span>
            <Badge status="default" />
            已忽略 <strong>{stats.ignored}</strong>
          </span>
        </Space>
      </div>

      <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, overflow: "auto", padding: "8px 0" }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: 32 }}>
              <Spin />
            </div>
          ) : risks.length === 0 ? (
            <Empty description="暂无风险项" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Collapse
              ghost
              activeKey={activeKeys}
              onChange={(keys) => setActiveKeys(keys as string[])}
              items={collapseItems}
            />
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
          {decisionModal?.type === "accepted" && (
            <Form.Item name="auto_create_node" label="自动创建异常节点" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
}
