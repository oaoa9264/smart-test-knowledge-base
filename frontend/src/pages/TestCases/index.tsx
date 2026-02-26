import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  message,
} from "antd";
import {
  createTestCase,
  deleteTestCase,
  fetchTestCase,
  fetchTestCases,
  updateTestCase,
} from "../../api/testcases";
import { fetchRuleTree } from "../../api/rules";
import { useAppStore } from "../../stores/appStore";
import type { RiskLevel, RulePath, RuleNode, TestCase } from "../../types";
import {
  getRiskLevelLabel,
  getTestCaseStatusLabel,
  riskLevelLabels,
} from "../../utils/enumLabels";

const riskTagColors: Record<RiskLevel, string> = {
  critical: "red",
  high: "volcano",
  medium: "gold",
  low: "green",
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

export default function TestCasesPage() {
  const { selectedProjectId, selectedRequirementId } = useAppStore();
  const [form] = Form.useForm();
  const selectedNodeIds = Form.useWatch<string[]>("bound_rule_node_ids", form) || [];
  const [editForm] = Form.useForm();
  const selectedEditNodeIds = Form.useWatch<string[]>("bound_rule_node_ids", editForm) || [];

  const [cases, setCases] = useState<TestCase[]>([]);
  const [nodes, setNodes] = useState<RuleNode[]>([]);
  const [paths, setPaths] = useState<RulePath[]>([]);
  const [viewingCase, setViewingCase] = useState<TestCase | null>(null);
  const [editingCase, setEditingCase] = useState<TestCase | null>(null);
  const [viewLoading, setViewLoading] = useState(false);
  const [deletingCaseId, setDeletingCaseId] = useState<number | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [createFormCollapsed, setCreateFormCollapsed] = useState(true);

  useEffect(() => {
    if (!selectedProjectId || !selectedRequirementId) {
      setCases([]);
      return;
    }
    fetchTestCases(selectedProjectId, selectedRequirementId)
      .then(setCases)
      .catch(() => message.error("加载用例失败"));
  }, [selectedProjectId, selectedRequirementId]);

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

  const nodeMap = useMemo(() => {
    const map = new Map<string, RuleNode>();
    nodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [nodes]);
  const pathMap = useMemo(() => {
    const map = new Map<string, RulePath>();
    paths.forEach((p) => map.set(p.id, p));
    return map;
  }, [paths]);

  const getNodeDisplay = (nodeId: string) => nodeMap.get(nodeId)?.content || nodeId;
  const getPathDisplay = (pathId: string) => {
    const path = pathMap.get(pathId);
    if (!path) return pathId;
    return path.node_sequence.map((nodeId) => getNodeDisplay(nodeId)).join(" -> ");
  };
  const getRiskTagColor = (risk?: string) => (risk ? riskTagColors[risk as RiskLevel] || "default" : "default");
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
      return new Set(paths.map((p) => p.id));
    }
    return new Set(
      paths
        .filter((p) => nodeIds.every((nodeId) => p.node_sequence.includes(nodeId)))
        .map((p) => p.id),
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
    if (!editingCase) return;
    const selectedPathIds = editForm.getFieldValue("bound_path_ids") || [];
    const filteredPathIds = selectedPathIds.filter((pathId: string) => matchedEditPathIdSet.has(pathId));
    if (filteredPathIds.length !== selectedPathIds.length) {
      editForm.setFieldsValue({ bound_path_ids: filteredPathIds });
      message.warning("已移除与已选规则节点不匹配的规则路径");
    }
    editForm.validateFields(["bound_path_ids"]).catch(() => undefined);
  }, [editForm, matchedEditPathIdSet, editingCase]);

  const nodeOptions = useMemo(
    () => nodes.map((n) => ({ label: `${n.content} (${riskLevelLabels[n.risk_level]})`, value: n.id })),
    [nodes],
  );
  const createPathOptions = useMemo(
    () =>
      paths.map((p) => ({
        label: p.node_sequence.map((nodeId) => nodeMap.get(nodeId)?.content || nodeId).join(" -> "),
        value: p.id,
      }))
      .filter((item) => matchedPathIdSet.has(item.value)),
    [paths, nodeMap, matchedPathIdSet],
  );
  const editPathOptions = useMemo(
    () =>
      paths.map((p) => ({
        label: p.node_sequence.map((nodeId) => nodeMap.get(nodeId)?.content || nodeId).join(" -> "),
        value: p.id,
      }))
      .filter((item) => matchedEditPathIdSet.has(item.value)),
    [paths, nodeMap, matchedEditPathIdSet],
  );

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
    if (!editingCase) return;
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
              initialValues={{ risk_level: "medium", status: "active", bound_rule_node_ids: [], bound_path_ids: [] }}
            >
              <Form.Item name="title" label="用例标题" rules={[{ required: true, message: "请输入标题" }]}>
                <Input />
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
                      if (!value.length) return;
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
              <Button type="link" onClick={() => setCreateFormCollapsed((prev) => !prev)}>
                {createFormCollapsed ? "展开新建用例" : "收起新建用例"}
              </Button>
            }
          >
            <Table<TestCase>
              rowKey="id"
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
                  if (!value.length) return;
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
          <Descriptions.Item label="执行步骤">{viewingCase?.steps}</Descriptions.Item>
          <Descriptions.Item label="预期结果">{viewingCase?.expected_result}</Descriptions.Item>
          <Descriptions.Item label="绑定节点">
            {viewingCase?.bound_rule_node_ids?.length ? (
              <Space wrap>
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
              <Space direction="vertical" size={4}>
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
