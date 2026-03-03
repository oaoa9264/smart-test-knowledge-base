import { useEffect, useMemo, useRef, useState } from "react";
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
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { InboxOutlined } from "@ant-design/icons";
import { analyzeArchitecture, importArchitectureAnalysis } from "../../api/architecture";
import { useAppStore } from "../../stores/appStore";
import type {
  ArchitectureAnalysisResult,
  ArchitectureImportOptions,
  DecisionTreeNode,
  RuleNode,
} from "../../types";
import MindMapWrapper, { type MindMapWrapperRef } from "../RuleTree/MindMapWrapper";
import { ruleNodesToMindMapData } from "../RuleTree/dataAdapter";
import { RULE_TREE_THEME } from "../RuleTree/mindMapTheme";

const analysisModeMeta: Record<string, { label: string; color: string; hint?: string }> = {
  llm: {
    label: "LLM",
    color: "blue",
  },
  mock: {
    label: "Mock",
    color: "default",
  },
  mock_fallback: {
    label: "Mock（LLM降级）",
    color: "orange",
    hint: "LLM 调用失败，已自动降级到规则模板分析",
  },
  unknown: {
    label: "未知",
    color: "default",
    hint: "后端未返回分析引擎标识，请重启后端后重试",
  },
};

const llmProviderMeta: Record<string, { label: string; color: string }> = {
  openai: { label: "OpenAI", color: "geekblue" },
  zhipu: { label: "Zhipu", color: "cyan" },
};

function resolveUploadFile(fileItem?: UploadFile): File | undefined {
  if (!fileItem) return undefined;

  const wrappedFile = (fileItem as UploadFile & { originFileObj?: File }).originFileObj;
  if (wrappedFile instanceof File) {
    return wrappedFile;
  }

  const rawFile = fileItem as unknown as File;
  if (rawFile instanceof File) {
    return rawFile;
  }

  return undefined;
}

function toRuleNodes(nodes: DecisionTreeNode[]): RuleNode[] {
  return nodes.map((node) => ({
    id: node.id,
    requirement_id: 0,
    parent_id: node.parent_id,
    node_type: node.type,
    content: node.content,
    risk_level: node.risk_level,
    version: 1,
    status: "active",
  }));
}

export default function ArchitectureAnalysisPage() {
  const { selectedProjectId, setSelectedRequirementId } = useAppStore();
  const [form] = Form.useForm();
  const mindMapRef = useRef<MindMapWrapperRef | null>(null);

  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<ArchitectureAnalysisResult | null>(null);
  const [importing, setImporting] = useState(false);
  const [importOptions, setImportOptions] = useState<ArchitectureImportOptions>({
    import_decision_tree: true,
  });

  const mindMapData = useMemo(
    () => ruleNodesToMindMapData(toRuleNodes(analysis?.decision_tree.nodes || [])),
    [analysis],
  );
  const modeKey = analysis?.analysis_mode && analysisModeMeta[analysis.analysis_mode] ? analysis.analysis_mode : "unknown";
  const modeMeta = analysisModeMeta[modeKey];
  const llmProviderKey = String(analysis?.llm_provider || "")
    .trim()
    .toLowerCase();
  const llmProviderTagMeta = llmProviderMeta[llmProviderKey];
  const llmProviderLabel = llmProviderTagMeta ? llmProviderTagMeta.label : analysis?.llm_provider;
  const showLlmProvider = modeKey === "llm" || modeKey === "mock_fallback";

  useEffect(() => {
    if (!analysis) return;
    requestAnimationFrame(() => {
      mindMapRef.current?.fitView();
    });
  }, [analysis?.id]);

  const startAnalyze = async () => {
    if (!selectedProjectId) {
      message.warning("请先在顶部选择项目");
      return;
    }

    const values = await form.validateFields();
    const descriptionText = String(values.description_text || "").trim();
    const uploadFile = resolveUploadFile(fileList[0]);
    if (!descriptionText && !uploadFile) {
      message.warning("请上传流程图或填写需求描述");
      return;
    }

    const formData = new FormData();
    formData.append("project_id", String(selectedProjectId));
    formData.append("title", values.title);
    formData.append("description_text", descriptionText);

    if (uploadFile) {
      formData.append("image", uploadFile);
    }

    setLoading(true);
    try {
      const result = await analyzeArchitecture(formData);
      setAnalysis(result);
      if (!result.analysis_mode) {
        message.warning("后端未返回分析引擎标识，请重启后端后重试");
      }
      message.success("需求拆解完成");
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
      message.success(`导入完成: 节点 ${result.imported_rule_nodes}`);
    } catch {
      message.error("导入失败");
    } finally {
      setImporting(false);
    }
  };

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        需求拆解
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
              <p style={{ color: "#75869a" }}>上传后可直接分析；如填写文字描述将与流程图联合分析</p>
            </Upload.Dragger>
          </Card>
        </Col>

        <Col span={16}>
          <Card title="需求描述">
            <Form layout="vertical" form={form}>
              <Form.Item name="title" label="需求标题" rules={[{ required: true, message: "请输入标题" }]}>
                <Input placeholder="例如：提现流程需求拆解" />
              </Form.Item>
              <Form.Item
                name="description_text"
                label="文字描述"
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
        <Alert style={{ marginTop: 16 }} type="info" message="完成分析后将在下方展示判断树" />
      ) : (
        <Card style={{ marginTop: 16 }}>
          <Space style={{ marginBottom: 12 }} wrap>
            <Typography.Text type="secondary">分析引擎</Typography.Text>
            <Tag color={modeMeta.color}>{modeMeta.label}</Tag>
            {showLlmProvider ? (
              llmProviderLabel ? (
                <Tag color={llmProviderTagMeta?.color || "default"}>{`LLM: ${llmProviderLabel}`}</Tag>
              ) : (
                <Tag color="default">LLM: 未识别</Tag>
              )
            ) : null}
            {modeMeta.hint ? <Typography.Text type="secondary">{modeMeta.hint}</Typography.Text> : null}
          </Space>

          <Typography.Text strong style={{ display: "inline-block", marginBottom: 8 }}>
            判断树
          </Typography.Text>
          <div style={{ height: 420, border: "1px solid #e2e8f0", borderRadius: 8 }}>
            <MindMapWrapper
              ref={mindMapRef}
              data={mindMapData}
              selectedNodeId={null}
              layout="logicalStructure"
              theme={RULE_TREE_THEME}
              editable={false}
            />
          </div>

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
            <Button type="primary" loading={importing} onClick={importResult}>
              导入到正式库
            </Button>
          </Space>
        </Card>
      )}
    </div>
  );
}
