import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  InputNumber,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { fetchRuleTree } from "../../api/rules";
import { fetchTestCases } from "../../api/testcases";
import { fetchRecoRunDetail, fetchRecoRuns, recommendRegression } from "../../api/recommendation";
import { useAppStore } from "../../stores/appStore";
import type {
  RecoMode,
  RecoResponse,
  RecoResultRow,
  RecoRun,
  RecoRunDetail,
  RuleNode,
  TestCaseStatus,
} from "../../types";
import { getRecoModeLabel, getTestCaseStatusLabel } from "../../utils/enumLabels";

interface RecoFormValues {
  mode: RecoMode;
  k: number;
  changed_node_ids?: string[];
  status_in?: TestCaseStatus[];
}

const modeOptions = [
  { label: getRecoModeLabel("FULL"), value: "FULL" as RecoMode },
  { label: getRecoModeLabel("CHANGE"), value: "CHANGE" as RecoMode },
];

const statusOptions = [
  { label: getTestCaseStatusLabel("active"), value: "active" as TestCaseStatus },
  { label: getTestCaseStatusLabel("needs_review"), value: "needs_review" as TestCaseStatus },
  { label: getTestCaseStatusLabel("invalidated"), value: "invalidated" as TestCaseStatus },
];

function toDateTimeText(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export default function RecommendationPage() {
  const navigate = useNavigate();
  const { selectedProjectId, selectedRequirementId } = useAppStore();
  const [form] = Form.useForm<RecoFormValues>();
  const mode = Form.useWatch("mode", form) || "FULL";

  const [running, setRunning] = useState(false);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingRunDetail, setLoadingRunDetail] = useState(false);
  const [loadingCases, setLoadingCases] = useState(false);

  const [nodes, setNodes] = useState<RuleNode[]>([]);
  const [caseTitleById, setCaseTitleById] = useState<Record<number, string>>({});
  const [result, setResult] = useState<RecoResponse | null>(null);
  const [runs, setRuns] = useState<RecoRun[]>([]);
  const [runDetail, setRunDetail] = useState<RecoRunDetail | null>(null);

  useEffect(() => {
    form.setFieldsValue({
      mode: "FULL",
      k: 10,
      changed_node_ids: [],
      status_in: ["active"],
    });
  }, [form]);

  useEffect(() => {
    if (!selectedRequirementId || !selectedProjectId) {
      setNodes([]);
      setCaseTitleById({});
      setRuns([]);
      setResult(null);
      setRunDetail(null);
      setLoadingCases(false);
      return;
    }

    fetchRuleTree(selectedRequirementId)
      .then((tree) => setNodes(tree.nodes))
      .catch(() => message.error("加载规则树失败"));

    setLoadingCases(true);
    fetchTestCases(selectedProjectId, selectedRequirementId)
      .then((data) => {
        const nextMap: Record<number, string> = {};
        data.forEach((item) => {
          nextMap[item.id] = item.title;
        });
        setCaseTitleById(nextMap);
      })
      .catch(() => message.error("加载用例列表失败"))
      .finally(() => setLoadingCases(false));
  }, [selectedProjectId, selectedRequirementId]);

  useEffect(() => {
    if (!selectedRequirementId) {
      setRuns([]);
      setResult(null);
      setRunDetail(null);
      return;
    }
    setResult(null);
    setRunDetail(null);
    loadRuns(selectedRequirementId);
  }, [selectedRequirementId]);

  const nodeNameMap = useMemo(() => {
    const map = new Map<string, string>();
    nodes.forEach((node) => map.set(node.id, node.content));
    return map;
  }, [nodes]);

  const nodeOptions = useMemo(
    () =>
      nodes.map((node) => ({
        label: `${node.content} (${node.id.slice(0, 8)})`,
        value: node.id,
      })),
    [nodes],
  );

  const hasAnyTestCase = useMemo(() => Object.keys(caseTitleById).length > 0, [caseTitleById]);

  const loadRuns = async (requirementId: number) => {
    setLoadingRuns(true);
    try {
      const data = await fetchRecoRuns(requirementId);
      setRuns(data);
      setRunDetail((prev) => (prev && data.some((item) => item.id === prev.run.id) ? prev : null));
    } catch {
      message.error("加载推荐历史失败");
    } finally {
      setLoadingRuns(false);
    }
  };

  const loadRunDetail = async (runId: number) => {
    setLoadingRunDetail(true);
    try {
      const data = await fetchRecoRunDetail(runId);
      setRunDetail(data);
    } catch {
      message.error("加载推荐详情失败");
    } finally {
      setLoadingRunDetail(false);
    }
  };

  const goToTestCase = (caseId: number) => {
    navigate(`/test-cases?focusCaseId=${caseId}`);
  };

  const startRecommend = async () => {
    if (!selectedRequirementId) {
      message.warning("请先选择需求");
      return;
    }
    if (loadingCases) {
      message.info("用例加载中，请稍候再试");
      return;
    }
    if (!hasAnyTestCase) {
      message.warning("当前需求下暂无测试用例，请先创建用例后再执行推荐");
      return;
    }

    const values = await form.validateFields();
    if (values.mode === "CHANGE" && (!values.changed_node_ids || values.changed_node_ids.length === 0)) {
      message.warning("变更回归模式请至少选择一个变更节点");
      return;
    }

    setRunning(true);
    try {
      const next = await recommendRegression({
        requirement_id: selectedRequirementId,
        mode: values.mode,
        k: values.k,
        changed_node_ids: values.mode === "CHANGE" ? values.changed_node_ids || [] : undefined,
        case_filter: values.status_in?.length ? { status_in: values.status_in } : undefined,
        cost_mode: "UNIT",
      });
      setResult(next);
      message.success("推荐完成");

      await loadRuns(selectedRequirementId);
      await loadRunDetail(next.run_id);
    } catch {
      message.error("执行推荐失败");
    } finally {
      setRunning(false);
    }
  };

  if (!selectedProjectId) {
    return <Alert type="info" message="请先选择项目" />;
  }

  if (!selectedRequirementId) {
    return <Alert type="info" message="请先选择需求，再执行回归推荐" />;
  }

  return (
    <div>
      <Card title="回归推荐参数" style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline">
          <Form.Item name="mode" label="模式" rules={[{ required: true }]}>
            <Select style={{ width: 200 }} options={modeOptions} />
          </Form.Item>
          <Form.Item name="k" label="回归K" rules={[{ required: true }]}>
            <InputNumber style={{ width: 120 }} min={1} max={200} />
          </Form.Item>
          <Form.Item name="status_in" label="用例状态过滤">
            <Select style={{ width: 220 }} mode="multiple" options={statusOptions} />
          </Form.Item>
          {mode === "CHANGE" ? (
            <Form.Item
              name="changed_node_ids"
              label="变更节点"
              rules={[{ required: true, message: "请选择变更节点" }]}
            >
              <Select style={{ width: 420 }} mode="multiple" options={nodeOptions} />
            </Form.Item>
          ) : null}
          <Form.Item>
            <Button type="primary" loading={running || loadingCases} onClick={startRecommend}>
              开始推荐
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {result ? (
        <Card title="本次推荐结果" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={6}>
              <Statistic title="选中用例数" value={result.summary.picked} suffix={`/ ${result.summary.k}`} />
            </Col>
            <Col span={6}>
              <Statistic title="覆盖风险值" value={result.summary.covered_risk} precision={2} />
            </Col>
            <Col span={6}>
              <Statistic title="目标风险值" value={result.summary.total_target_risk} precision={2} />
            </Col>
            <Col span={6}>
              <Typography.Text type="secondary">风险覆盖率</Typography.Text>
              <Progress percent={Math.round((result.summary.coverage_ratio || 0) * 100)} />
            </Col>
          </Row>

          <Table
            style={{ marginTop: 12 }}
            rowKey={(item) => `${item.rank}-${item.case_id}`}
            pagination={{ pageSize: 6 }}
            dataSource={result.cases}
            columns={[
              { title: "排名", dataIndex: "rank", width: 72 },
              {
                title: "用例",
                dataIndex: "case_id",
                render: (value: number) => `${caseTitleById[value] || "未命名用例"} (#${value})`,
              },
              { title: "收益风险值", dataIndex: "gain_risk", render: (value: number) => value.toFixed(2) },
              {
                title: "新增覆盖节点",
                dataIndex: "gain_nodes",
                render: (nodeIds: string[]) =>
                  nodeIds.length ? nodeIds.map((nodeId) => nodeNameMap.get(nodeId) || nodeId).join(" / ") : "-",
              },
              {
                title: "解释",
                dataIndex: "why_selected",
              },
              {
                title: "操作",
                width: 96,
                render: (_, row) => (
                  <Button type="link" onClick={() => goToTestCase(row.case_id)}>
                    查看用例
                  </Button>
                ),
              },
            ]}
          />

          <Table
            style={{ marginTop: 12 }}
            rowKey="node_id"
            size="small"
            pagination={{ pageSize: 5 }}
            dataSource={result.remaining_high_risk_gaps}
            columns={[
              {
                title: "剩余高风险缺口节点",
                dataIndex: "node_id",
                render: (nodeId: string) => nodeNameMap.get(nodeId) || nodeId,
              },
              {
                title: "风险值",
                dataIndex: "risk",
                width: 160,
                render: (value: number) => <Tag color="red">{value.toFixed(2)}</Tag>,
              },
            ]}
          />
        </Card>
      ) : null}

      <Card title="历史推荐记录">
        <Table
          rowKey="id"
          loading={loadingRuns}
          size="small"
          dataSource={runs}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "Run ID", dataIndex: "id", width: 96 },
            {
              title: "模式",
              dataIndex: "mode",
              width: 110,
              render: (value: RecoMode) => <Tag color={value === "CHANGE" ? "gold" : "blue"}>{getRecoModeLabel(value)}</Tag>,
            },
            { title: "K", dataIndex: "k", width: 80 },
            {
              title: "覆盖率",
              dataIndex: "coverage_ratio",
              render: (value: number) => `${Math.round((value || 0) * 100)}%`,
            },
            {
              title: "时间",
              dataIndex: "created_at",
              width: 200,
              render: (value: string) => toDateTimeText(value),
            },
            {
              title: "操作",
              key: "action",
              width: 90,
              render: (_, record: RecoRun) => (
                <Button type="link" onClick={() => loadRunDetail(record.id)}>
                  查看
                </Button>
              ),
            },
          ]}
        />
      </Card>

      {runDetail ? (
        <Card title={`运行详情 #${runDetail.run.id}`} style={{ marginTop: 16 }} loading={loadingRunDetail}>
          <Descriptions size="small" column={4}>
            <Descriptions.Item label="模式">{getRecoModeLabel(runDetail.run.mode)}</Descriptions.Item>
            <Descriptions.Item label="回归K">{runDetail.run.k}</Descriptions.Item>
            <Descriptions.Item label="覆盖风险">{runDetail.run.covered_risk.toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="风险覆盖率">
              {Math.round((runDetail.run.coverage_ratio || 0) * 100)}%
            </Descriptions.Item>
          </Descriptions>

          <Table
            style={{ marginTop: 12 }}
            size="small"
            rowKey={(item) => item.id}
            dataSource={runDetail.results}
            pagination={{ pageSize: 8 }}
            columns={[
              { title: "Rank", dataIndex: "rank", width: 72 },
              {
                title: "用例",
                dataIndex: "case_id",
                render: (value: number) => `${caseTitleById[value] || "未命名用例"} (#${value})`,
              },
              {
                title: "收益风险值",
                dataIndex: "gain_risk",
                width: 130,
                render: (value: number) => value.toFixed(2),
              },
              {
                title: "关键贡献节点",
                dataIndex: "top_contributors",
                render: (items: RecoResultRow["top_contributors"]) =>
                  items.length ? (
                    <Space size={[4, 4]} wrap>
                      {items.map((item) => (
                        <Tag key={`${item.node_id}-${item.risk}`}>
                          {(nodeNameMap.get(item.node_id) || item.node_id) + ` (${item.risk.toFixed(1)})`}
                        </Tag>
                      ))}
                    </Space>
                  ) : (
                    "-"
                  ),
              },
              { title: "解释", dataIndex: "why_selected" },
              {
                title: "操作",
                width: 96,
                render: (_, row: RecoResultRow) => (
                  <Button type="link" onClick={() => goToTestCase(row.case_id)}>
                    查看用例
                  </Button>
                ),
              },
            ]}
          />
        </Card>
      ) : null}
    </div>
  );
}
