import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  Checkbox,
  Collapse,
  Divider,
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
  BookOutlined,
  BranchesOutlined,
} from "@ant-design/icons";
import type { RiskCategory, RiskDecisionType, RiskItem, RiskSource } from "../../types";
import { analyzeRisks, clarifyRisk, decideRisk, deleteRisk, fetchRisks } from "../../api/risks";
import { fetchProductDocs, suggestDocUpdate } from "../../api/productDocs";
import { useAppStore } from "../../stores/appStore";

const categoryLabels: Record<RiskCategory, string> = {
  input_validation: "输入校验",
  flow_gap: "流程缺口",
  data_integrity: "数据完整性",
  boundary: "边界条件",
  security: "安全风险",
  product_knowledge: "产品知识",
};

const categoryColors: Record<RiskCategory, string> = {
  input_validation: "orange",
  flow_gap: "red",
  data_integrity: "purple",
  boundary: "blue",
  security: "volcano",
  product_knowledge: "cyan",
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

const sourceLabels: Record<RiskSource, string> = {
  rule_tree: "技术风险",
  product_knowledge: "产品知识风险",
};

const sourceIcons: Record<RiskSource, React.ReactNode> = {
  rule_tree: <BranchesOutlined />,
  product_knowledge: <BookOutlined />,
};

type RiskPanelProps = {
  requirementId: number | null;
  onNodeLocate?: (nodeId: string) => void;
  onRiskConverted?: () => void;
  onRisksChange?: (risks: RiskItem[]) => void;
};

export default function RiskPanel({ requirementId, onNodeLocate, onRiskConverted, onRisksChange }: RiskPanelProps) {
  const { selectedProjectId, projects } = useAppStore();
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [autoCreateNode, setAutoCreateNode] = useState(true);

  const [decisionModal, setDecisionModal] = useState<{
    risk: RiskItem;
    type: "accepted" | "ignored";
  } | null>(null);
  const [form] = Form.useForm();

  const [clarifyModal, setClarifyModal] = useState<RiskItem | null>(null);
  const [clarifyForm] = Form.useForm();

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

  const groupedBySource = useMemo(() => {
    const groups: Record<RiskSource, Record<string, RiskItem[]>> = {
      rule_tree: {},
      product_knowledge: {},
    };
    for (const risk of risks) {
      const source = risk.risk_source || "rule_tree";
      const cat = risk.category;
      if (!groups[source]) groups[source] = {};
      if (!groups[source][cat]) groups[source][cat] = [];
      groups[source][cat].push(risk);
    }
    return groups;
  }, [risks]);

  const [activeKeys, setActiveKeys] = useState<string[]>([]);

  useEffect(() => {
    const keys: string[] = [];
    for (const source of ["rule_tree", "product_knowledge"] as RiskSource[]) {
      for (const cat of Object.keys(groupedBySource[source] || {})) {
        keys.push(`${source}_${cat}`);
      }
    }
    setActiveKeys(keys);
  }, [groupedBySource]);

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

  const buildCollapseItems = (source: RiskSource) => {
    const cats = groupedBySource[source] || {};
    return Object.entries(cats).map(([category, items]) => ({
      key: `${source}_${category}`,
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
          {items.map(renderRiskCard)}
        </div>
      ),
    }));
  };

  const ruleTreeItems = buildCollapseItems("rule_tree");
  const productItems = buildCollapseItems("product_knowledge");

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
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8 }}>
          <Switch size="small" checked={autoCreateNode} onChange={setAutoCreateNode} />
          <Tooltip title="开启后，接受风险时自动在规则树上创建对应的异常节点">
            <Typography.Text type="secondary" style={{ fontSize: 12, cursor: "help" }}>
              接受时自动创建节点
            </Typography.Text>
          </Tooltip>
        </div>
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
            <>
              {ruleTreeItems.length > 0 && (
                <>
                  <div style={{ padding: "4px 16px", display: "flex", alignItems: "center", gap: 6 }}>
                    {sourceIcons.rule_tree}
                    <Typography.Text strong style={{ fontSize: 13 }}>{sourceLabels.rule_tree}</Typography.Text>
                    <Badge count={risks.filter(r => (r.risk_source || "rule_tree") === "rule_tree").length} style={{ backgroundColor: "#1890ff" }} />
                  </div>
                  <Collapse
                    ghost
                    activeKey={activeKeys}
                    onChange={(keys) => setActiveKeys(keys as string[])}
                    items={ruleTreeItems}
                  />
                </>
              )}
              {productItems.length > 0 && (
                <>
                  {ruleTreeItems.length > 0 && <Divider style={{ margin: "8px 0" }} />}
                  <div style={{ padding: "4px 16px", display: "flex", alignItems: "center", gap: 6 }}>
                    {sourceIcons.product_knowledge}
                    <Typography.Text strong style={{ fontSize: 13, color: "#13c2c2" }}>{sourceLabels.product_knowledge}</Typography.Text>
                    <Badge count={risks.filter(r => r.risk_source === "product_knowledge").length} style={{ backgroundColor: "#13c2c2" }} />
                  </div>
                  <Collapse
                    ghost
                    activeKey={activeKeys}
                    onChange={(keys) => setActiveKeys(keys as string[])}
                    items={productItems}
                  />
                </>
              )}
            </>
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
