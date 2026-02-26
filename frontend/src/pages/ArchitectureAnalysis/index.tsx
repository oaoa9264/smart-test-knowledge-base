import { useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Form,
  Input,
  Row,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { InboxOutlined } from "@ant-design/icons";
import ReactFlow, { Background, Controls, MiniMap, Node, Edge, PanOnScrollMode } from "reactflow";
import ReactMarkdown from "react-markdown";
import "reactflow/dist/style.css";
import { analyzeArchitecture, importArchitectureAnalysis } from "../../api/architecture";
import { useAppStore } from "../../stores/appStore";
import type {
  ArchitectureAnalysisResult,
  ArchitectureImportOptions,
  DecisionTreeNode,
  RiskPoint,
  GeneratedTestCase,
} from "../../types";
import { getRiskLevelLabel } from "../../utils/enumLabels";

const riskTagColor: Record<string, string> = {
  critical: "red",
  high: "volcano",
  medium: "gold",
  low: "green",
};

function toFlowNodes(nodes: DecisionTreeNode[]): Node[] {
  const byId = new Map(nodes.map((item) => [item.id, item]));
  const levelMap = new Map<string, number>();
  const siblingMap: Record<string, number> = {};

  const getDepth = (node: DecisionTreeNode): number => {
    if (!node.parent_id) return 0;
    if (levelMap.has(node.id)) return levelMap.get(node.id) || 0;
    const parent = byId.get(node.parent_id);
    if (!parent) return 0;
    const depth = getDepth(parent) + 1;
    levelMap.set(node.id, depth);
    return depth;
  };

  return nodes.map((node) => {
    const depth = getDepth(node);
    const siblingKey = node.parent_id || "root";
    siblingMap[siblingKey] = (siblingMap[siblingKey] || 0) + 1;
    const order = siblingMap[siblingKey] - 1;

    return {
      id: node.id,
      position: { x: 220 * depth + 40, y: 120 * order + 40 },
      data: { label: node.content },
      style: {
        width: 220,
        borderRadius: 10,
        border: `1px solid ${riskTagColor[node.risk_level] || "#6f6f6f"}`,
        background: "#f8fbff",
        padding: 10,
      },
    };
  });
}

function toFlowEdges(nodes: DecisionTreeNode[]): Edge[] {
  return nodes
    .filter((node) => !!node.parent_id)
    .map((node) => ({
      id: `${node.parent_id}-${node.id}`,
      source: node.parent_id as string,
      target: node.id,
    }));
}

export default function ArchitectureAnalysisPage() {
  const { selectedProjectId, setSelectedRequirementId } = useAppStore();
  const [form] = Form.useForm();

  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<ArchitectureAnalysisResult | null>(null);
  const [importing, setImporting] = useState(false);
  const [importOptions, setImportOptions] = useState<ArchitectureImportOptions>({
    import_decision_tree: true,
    import_test_cases: true,
    import_risk_points: true,
  });

  const flowNodes = useMemo(() => toFlowNodes(analysis?.decision_tree.nodes || []), [analysis]);
  const flowEdges = useMemo(() => toFlowEdges(analysis?.decision_tree.nodes || []), [analysis]);

  const startAnalyze = async () => {
    if (!selectedProjectId) {
      message.warning("请先在顶部选择项目");
      return;
    }

    const values = await form.validateFields();
    const formData = new FormData();
    formData.append("project_id", String(selectedProjectId));
    formData.append("title", values.title);
    formData.append("description_text", values.description_text);

    if (fileList[0]?.originFileObj) {
      formData.append("image", fileList[0].originFileObj as File);
    }

    setLoading(true);
    try {
      const result = await analyzeArchitecture(formData);
      setAnalysis(result);
      message.success("架构拆解完成");
    } catch {
      message.error("分析失败，请检查输入后重试");
    } finally {
      setLoading(false);
    }
  };

  const importResult = async () => {
    if (!analysis?.id) {
      message.warning("请先完成分析");
      return;
    }

    setImporting(true);
    try {
      const result = await importArchitectureAnalysis(analysis.id, importOptions);
      if (result.requirement_id) {
        setSelectedRequirementId(result.requirement_id);
      }
      message.success(
        `导入完成: 节点 ${result.imported_rule_nodes} / 用例 ${result.imported_test_cases} / 风险标注 ${result.updated_risk_nodes}`,
      );
    } catch {
      message.error("导入失败");
    } finally {
      setImporting(false);
    }
  };

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        AI 辅助架构拆解
      </Typography.Title>

      <Row gutter={16}>
        <Col span={8}>
          <Card title="上传流程图">
            <Upload.Dragger
              accept="image/*"
              fileList={fileList}
              beforeUpload={(file) => {
                setFileList([file]);
                return false;
              }}
              onRemove={() => {
                setFileList([]);
              }}
              maxCount={1}
            >
              <p>
                <InboxOutlined style={{ fontSize: 28 }} />
              </p>
              <p>点击或拖拽上传流程图</p>
              <p style={{ color: "#75869a" }}>可选项，不上传则仅基于文字描述分析</p>
            </Upload.Dragger>
          </Card>
        </Col>

        <Col span={16}>
          <Card title="架构描述">
            <Form
              layout="vertical"
              form={form}
              initialValues={{
                title: "系统架构拆解",
              }}
            >
              <Form.Item name="title" label="分析标题" rules={[{ required: true, message: "请输入标题" }]}>
                <Input placeholder="例如：提现流程架构拆解" />
              </Form.Item>
              <Form.Item
                name="description_text"
                label="文字描述"
                rules={[{ required: true, message: "请输入架构描述" }]}
              >
                <Input.TextArea
                  rows={8}
                  placeholder="例如：用户提交提现申请。如果用户未实名认证，则拒绝提现。若已实名认证，检查余额..."
                />
              </Form.Item>
              <Button type="primary" loading={loading} onClick={startAnalyze}>
                开始分析
              </Button>
            </Form>
          </Card>
        </Col>
      </Row>

      {!analysis ? (
        <Alert style={{ marginTop: 16 }} type="info" message="完成分析后将在下方展示判断树、测试方案、风险点和用例矩阵" />
      ) : (
        <Card style={{ marginTop: 16 }}>
          <Tabs
            items={[
              {
                key: "tree",
                label: "判断树",
                children: (
                  <div style={{ height: 420, border: "1px solid #e2e8f0", borderRadius: 8 }}>
                    <ReactFlow
                      nodes={flowNodes}
                      edges={flowEdges}
                      panOnDrag
                      panOnScroll
                      panOnScrollMode={PanOnScrollMode.Free}
                      fitView
                      fitViewOptions={{ padding: 0.2, minZoom: 0.05 }}
                      minZoom={0.05}
                    >
                      <Background gap={14} size={1} />
                      <MiniMap />
                      <Controls />
                    </ReactFlow>
                  </div>
                ),
              },
              {
                key: "plan",
                label: "测试方案",
                children: (
                  <Card>
                    <ReactMarkdown>{analysis.test_plan.markdown}</ReactMarkdown>
                  </Card>
                ),
              },
              {
                key: "risk",
                label: "关键风险点",
                children: (
                  <Space direction="vertical" style={{ width: "100%" }}>
                    {analysis.risk_points.map((item: RiskPoint) => (
                      <Card key={item.id} size="small">
                        <Space>
                          <Tag color={riskTagColor[item.severity]}>{getRiskLevelLabel(item.severity)}</Tag>
                          <Typography.Text strong>{item.description}</Typography.Text>
                        </Space>
                        <Typography.Paragraph style={{ marginTop: 8, marginBottom: 0 }}>
                          缓解建议: {item.mitigation}
                        </Typography.Paragraph>
                      </Card>
                    ))}
                  </Space>
                ),
              },
              {
                key: "cases",
                label: "用例矩阵",
                children: (
                  <Table<GeneratedTestCase>
                    rowKey={(row) => `${row.title}-${row.steps}`}
                    pagination={{ pageSize: 6 }}
                    dataSource={analysis.test_cases}
                    columns={[
                      { title: "标题", dataIndex: "title" },
                      { title: "步骤", dataIndex: "steps" },
                      { title: "预期", dataIndex: "expected_result" },
                      {
                        title: "风险",
                        dataIndex: "risk_level",
                        width: 120,
                        render: (risk) => <Tag color={riskTagColor[risk]}>{getRiskLevelLabel(risk)}</Tag>,
                      },
                    ]}
                  />
                ),
              },
            ]}
          />

          <Space style={{ marginTop: 12 }} wrap>
            <Checkbox
              checked={importOptions.import_decision_tree}
              onChange={(e) =>
                setImportOptions((prev) => ({
                  ...prev,
                  import_decision_tree: e.target.checked,
                }))
              }
            >
              导入判断树
            </Checkbox>
            <Checkbox
              checked={importOptions.import_test_cases}
              onChange={(e) =>
                setImportOptions((prev) => ({
                  ...prev,
                  import_test_cases: e.target.checked,
                }))
              }
            >
              导入用例矩阵
            </Checkbox>
            <Checkbox
              checked={importOptions.import_risk_points}
              onChange={(e) =>
                setImportOptions((prev) => ({
                  ...prev,
                  import_risk_points: e.target.checked,
                }))
              }
            >
              标注风险等级
            </Checkbox>
            <Button type="primary" loading={importing} onClick={importResult}>
              导入到正式库
            </Button>
          </Space>
        </Card>
      )}
    </div>
  );
}
