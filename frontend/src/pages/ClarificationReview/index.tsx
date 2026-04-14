import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from "antd";
import {
  AppstoreOutlined,
  BugOutlined,
  CodeOutlined,
  DeleteOutlined,
  ShopOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  analyzeClarificationReview,
  deleteClarificationReviewRecord,
  fetchClarificationReviewRecord,
  fetchClarificationReviewRecords,
} from "../../api/clarificationReview";
import { getErrorMessage } from "../../api/client";
import type {
  ClarificationReviewAnalyzeRequest,
  ClarificationReviewQuestionItem,
  ClarificationReviewRoleDescriptorItem,
  ClarificationReviewRecord,
  ClarificationReviewRecordSummary,
} from "../../types";


const DEFAULT_RULE_TEXT = `请不要假设历史规则已经完整，帮我做以下分析：

1. 根据已有信息，推测这类老项目最可能存在的历史规则和隐含约束
2. 指出哪些关键规则当前缺失，导致这份需求无法被准确分析
3. 输出"必须优先确认的问题清单"，并按角色分类：
   - 问产品
   - 问开发
   - 问测试
   - 问运营/业务
4. 对每个问题说明为什么要问、不问会有什么风险
5. 在历史规则不完整的前提下，先输出目前已经可以识别的需求缺陷
6. 对无法确认的部分，以"风险假设"的方式列出，不要跳过

补充要求：
- 追问问题必须针对我填写的需求内容，禁止泛泛提问
- 推测的历史规则要说明推导依据，不要凭空猜测
- 优先关注：流程断裂、边界未定义、角色职责不清、数据流向不明的问题`;

const { TextArea } = Input;

type ClarificationReviewFormValues = ClarificationReviewAnalyzeRequest;
type ClarificationRoleKey = string;

type RoleMeta = {
  title: string;
  shortTitle: string;
  helper: string;
  color: string;
  softColor: string;
  borderColor: string;
  emptyText: string;
  icon: JSX.Element;
};

type QuestionGroup = RoleMeta & {
  roleKey: string;
  items: ClarificationReviewQuestionItem[];
  source: string;
  isExtra: boolean;
};

const KNOWN_ROLE_META: Record<string, RoleMeta> = {
  产品: {
    title: "产品需要确认",
    shortTitle: "产品",
    helper: "范围、口径、业务规则",
    color: "#1d4ed8",
    softColor: "#eff6ff",
    borderColor: "#bfdbfe",
    emptyText: "当前没有产品侧待确认问题",
    icon: <AppstoreOutlined />,
  },
  开发: {
    title: "开发需要确认",
    shortTitle: "开发",
    helper: "链路、实现、数据流转",
    color: "#0f766e",
    softColor: "#ecfdf5",
    borderColor: "#99f6e4",
    emptyText: "当前没有开发侧待确认问题",
    icon: <CodeOutlined />,
  },
  测试: {
    title: "测试需要确认",
    shortTitle: "测试",
    helper: "校验口径、覆盖边界、回归点",
    color: "#a16207",
    softColor: "#fffbeb",
    borderColor: "#fde68a",
    emptyText: "当前没有测试侧待确认问题",
    icon: <BugOutlined />,
  },
  "运营/业务": {
    title: "运营/业务需要确认",
    shortTitle: "运营/业务",
    helper: "策略、配置、落地约束",
    color: "#7c3aed",
    softColor: "#f5f3ff",
    borderColor: "#ddd6fe",
    emptyText: "当前没有运营/业务侧待确认问题",
    icon: <ShopOutlined />,
  },
};

const FALLBACK_ROLE_STYLES = [
  { color: "#b45309", softColor: "#fff7ed", borderColor: "#fdba74" },
  { color: "#be123c", softColor: "#fff1f2", borderColor: "#fda4af" },
  { color: "#0f766e", softColor: "#f0fdfa", borderColor: "#99f6e4" },
  { color: "#1d4ed8", softColor: "#eff6ff", borderColor: "#93c5fd" },
  { color: "#6d28d9", softColor: "#f5f3ff", borderColor: "#c4b5fd" },
  { color: "#15803d", softColor: "#f0fdf4", borderColor: "#86efac" },
];

function toDateTimeText(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function hasMeaningfulText(value: string | null | undefined): boolean {
  const normalized = String(value || "").trim();
  return Boolean(normalized && normalized !== "-");
}

function ProviderTag({ provider }: { provider: string | null }) {
  if (!provider) return null;
  const normalized = provider.trim().toLowerCase();
  const color = normalized === "openai" ? "geekblue" : normalized === "zhipu" ? "cyan" : "default";
  return <Tag color={color}>{`LLM: ${provider}`}</Tag>;
}

function getRoleMeta(roleKey: string, index: number): RoleMeta {
  const knownMeta = KNOWN_ROLE_META[roleKey];
  if (knownMeta) return knownMeta;

  const style = FALLBACK_ROLE_STYLES[index % FALLBACK_ROLE_STYLES.length];
  return {
    title: `${roleKey}需要确认`,
    shortTitle: roleKey,
    helper: "自定义角色追问",
    color: style.color,
    softColor: style.softColor,
    borderColor: style.borderColor,
    emptyText: `当前没有${roleKey}待确认问题`,
    icon: <TeamOutlined />,
  };
}

function getRoleDescriptors(record: ClarificationReviewRecord | null): ClarificationReviewRoleDescriptorItem[] {
  const result = record?.result;
  if (!result) return [];

  const configuredRoles = result.configured_roles || [];
  const descriptors = [...(result.role_descriptors || [])];
  const seen = new Set(descriptors.map((item) => item.key));

  configuredRoles.forEach((roleKey) => {
    if (seen.has(roleKey)) return;
    descriptors.push({ key: roleKey, source: "rule_text" });
    seen.add(roleKey);
  });

  Object.keys(result.priority_questions_by_role || {}).forEach((roleKey) => {
    if (seen.has(roleKey)) return;
    descriptors.push({
      key: roleKey,
      source: configuredRoles.includes(roleKey) ? "rule_text" : "llm_extra",
    });
    seen.add(roleKey);
  });

  return descriptors;
}

function QuestionMetaRow({
  label,
  value,
  accentColor,
}: {
  label: string;
  value: string;
  accentColor: string;
}) {
  if (!hasMeaningfulText(value)) return null;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        flexWrap: "wrap",
      }}
    >
      <Tag
        style={{
          marginInlineEnd: 0,
          borderRadius: 999,
          color: accentColor,
          borderColor: `${accentColor}33`,
          background: `${accentColor}12`,
        }}
      >
        {label}
      </Tag>
      <Typography.Text type="secondary" style={{ flex: 1, minWidth: 0 }}>
        {value}
      </Typography.Text>
    </div>
  );
}

function RoleQuestionSection({
  group,
}: {
  group: QuestionGroup;
}) {
  const meta = group;
  const items = group.items;

  return (
    <Card
      size="small"
      bodyStyle={{ padding: items.length === 0 ? 16 : 20 }}
      style={{
        borderRadius: 16,
        borderColor: meta.borderColor,
        boxShadow: "0 10px 24px rgba(17, 43, 68, 0.05)",
      }}
    >
      {items.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={meta.emptyText} />
      ) : (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {items.map((item, index) => (
            <div
              key={`${group.roleKey}-${index}`}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 12,
                padding: 16,
                borderRadius: 14,
                border: `1px solid ${meta.borderColor}`,
                background: meta.softColor,
              }}
            >
              <div
                style={{
                  flex: "0 0 32px",
                  width: 32,
                  height: 32,
                  lineHeight: "32px",
                  borderRadius: 999,
                  textAlign: "center",
                  fontWeight: 700,
                  color: meta.color,
                  background: "#ffffff",
                  border: `1px solid ${meta.borderColor}`,
                  boxShadow: "0 6px 16px rgba(17, 43, 68, 0.06)",
                }}
              >
                {index + 1}
              </div>
              <Space direction="vertical" size={10} style={{ width: "100%" }}>
                <Typography.Text strong style={{ fontSize: 16, lineHeight: 1.6 }}>
                  {item.question}
                </Typography.Text>
                <QuestionMetaRow label="为什么要问" value={item.why_ask} accentColor={meta.color} />
                <QuestionMetaRow label="不问风险" value={item.risk_if_unasked} accentColor={meta.color} />
              </Space>
            </div>
          ))}
        </Space>
      )}
    </Card>
  );
}

type RuleLikeTheme = {
  color: string;
  softColor: string;
  borderColor: string;
};

const RULE_LIKE_THEMES: Record<string, RuleLikeTheme> = {
  history: { color: "#1d4ed8", softColor: "#eff6ff", borderColor: "#bfdbfe" },
  missing: { color: "#b45309", softColor: "#fffbeb", borderColor: "#fde68a" },
  gap: { color: "#be123c", softColor: "#fff1f2", borderColor: "#fecdd3" },
  assumption: { color: "#7c3aed", softColor: "#f5f3ff", borderColor: "#ddd6fe" },
};

type RuleLikeMetaField = { label: string; value: string };

function RuleLikeList<T extends object>({
  title,
  emptyText,
  themeKey,
  items,
  getTitle,
  getMetaFields,
}: {
  title: string;
  emptyText: string;
  themeKey: string;
  items: T[];
  getTitle: (item: T) => string;
  getMetaFields: (item: T) => RuleLikeMetaField[];
}) {
  const theme = RULE_LIKE_THEMES[themeKey] || RULE_LIKE_THEMES.history;

  return (
    <Card
      size="small"
      bodyStyle={{ padding: items.length === 0 ? 16 : 20 }}
      style={{
        borderRadius: 16,
        borderColor: theme.borderColor,
        boxShadow: "0 10px 24px rgba(17, 43, 68, 0.05)",
      }}
      title={
        <Space size={8} align="center">
          <Typography.Text strong>{title}</Typography.Text>
          <Tag
            style={{
              marginInlineEnd: 0,
              borderRadius: 999,
              color: theme.color,
              borderColor: `${theme.color}30`,
              background: theme.softColor,
            }}
          >
            {`${items.length} 条`}
          </Tag>
        </Space>
      }
    >
      {items.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
      ) : (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {items.map((item, index) => (
            <div
              key={`${title}-${index}`}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 12,
                padding: 16,
                borderRadius: 14,
                border: `1px solid ${theme.borderColor}`,
                background: theme.softColor,
              }}
            >
              <div
                style={{
                  flex: "0 0 28px",
                  width: 28,
                  height: 28,
                  lineHeight: "28px",
                  borderRadius: 999,
                  textAlign: "center",
                  fontWeight: 700,
                  fontSize: 13,
                  color: theme.color,
                  background: "#ffffff",
                  border: `1px solid ${theme.borderColor}`,
                  boxShadow: "0 4px 12px rgba(17, 43, 68, 0.06)",
                }}
              >
                {index + 1}
              </div>
              <Space direction="vertical" size={8} style={{ flex: 1, minWidth: 0 }}>
                <Typography.Text strong style={{ fontSize: 14, lineHeight: 1.6 }}>
                  {getTitle(item)}
                </Typography.Text>
                {getMetaFields(item).map((field) =>
                  hasMeaningfulText(field.value) ? (
                    <div
                      key={field.label}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 8,
                        flexWrap: "wrap",
                      }}
                    >
                      <Tag
                        style={{
                          marginInlineEnd: 0,
                          borderRadius: 999,
                          color: theme.color,
                          borderColor: `${theme.color}33`,
                          background: `${theme.color}12`,
                        }}
                      >
                        {field.label}
                      </Tag>
                      <Typography.Text type="secondary" style={{ flex: 1, minWidth: 0 }}>
                        {field.value}
                      </Typography.Text>
                    </div>
                  ) : null,
                )}
              </Space>
            </div>
          ))}
        </Space>
      )}
    </Card>
  );
}

export default function ClarificationReviewPage() {
  const [form] = Form.useForm<ClarificationReviewFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [records, setRecords] = useState<ClarificationReviewRecordSummary[]>([]);
  const [activeRecord, setActiveRecord] = useState<ClarificationReviewRecord | null>(null);
  const [expandedRoles, setExpandedRoles] = useState<string[]>([]);

  useEffect(() => {
    form.setFieldsValue({
      requirement_text: "",
      current_surface_flow: "",
      involved_modules: "",
      known_background: "",
      unknowns: "",
      rule_text: DEFAULT_RULE_TEXT,
    });
    void loadRecords();
  }, [form]);

  const loadRecords = async (nextActiveId?: number) => {
    setHistoryLoading(true);
    try {
      const data = await fetchClarificationReviewRecords(20);
      setRecords(data);
      const targetId = nextActiveId ?? activeRecord?.id ?? data[0]?.id;
      if (targetId) {
        await loadRecordDetail(targetId);
      } else {
        setActiveRecord(null);
      }
    } catch (error) {
      message.error(getErrorMessage(error, "加载最近记录失败"));
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadRecordDetail = async (recordId: number) => {
    setDetailLoading(true);
    try {
      const record = await fetchClarificationReviewRecord(recordId);
      setActiveRecord(record);
      form.setFieldsValue({
        ...record.input_payload,
        rule_text: record.rule_text,
      });
    } catch (error) {
      message.error(getErrorMessage(error, "加载记录详情失败"));
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDelete = (recordId: number) => {
    Modal.confirm({
      title: "确认删除",
      content: `确定要删除记录 #${recordId} 吗？删除后不可恢复。`,
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await deleteClarificationReviewRecord(recordId);
          message.success("删除成功");
          if (activeRecord?.id === recordId) {
            setActiveRecord(null);
          }
          await loadRecords();
        } catch (error) {
          message.error(getErrorMessage(error, "删除失败"));
        }
      },
    });
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const knownFields = [
      values.requirement_text,
      values.current_surface_flow,
      values.involved_modules,
      values.known_background,
      values.unknowns,
    ];

    if (!knownFields.some((item) => item.trim())) {
      message.warning("请至少填写一项已知信息");
      return;
    }

    setSubmitting(true);
    try {
      const record = await analyzeClarificationReview({
        requirement_text: values.requirement_text.trim(),
        current_surface_flow: values.current_surface_flow.trim(),
        involved_modules: values.involved_modules.trim(),
        known_background: values.known_background.trim(),
        unknowns: values.unknowns.trim(),
        rule_text: values.rule_text.trim(),
      });
      setActiveRecord(record);
      await loadRecords(record.id);
      if (record.llm_status === "failed") {
        message.warning(record.llm_message || "模型调用失败，已保存空结果记录");
      } else {
        message.success("追问分析完成");
      }
    } catch (error) {
      message.error(getErrorMessage(error, "追问分析失败"));
    } finally {
      setSubmitting(false);
    }
  };

  const summaryMarkdown = useMemo(() => activeRecord?.result.summary_markdown || "", [activeRecord]);
  const questionGroups = useMemo(
    () =>
      getRoleDescriptors(activeRecord).map((descriptor, index) => ({
        roleKey: descriptor.key,
        ...getRoleMeta(descriptor.key, index),
        items: activeRecord?.result.priority_questions_by_role[descriptor.key] || [],
        source: descriptor.source,
        isExtra: descriptor.source === "llm_extra",
      })),
    [activeRecord],
  );

  useEffect(() => {
    const firstRoleWithQuestions = questionGroups.find((group) => group.items.length > 0)?.roleKey;
    setExpandedRoles(firstRoleWithQuestions ? [firstRoleWithQuestions] : []);
  }, [questionGroups]);

  const copySummary = async () => {
    if (!summaryMarkdown.trim()) {
      message.warning("暂无可复制的摘要");
      return;
    }
    if (!navigator.clipboard?.writeText) {
      message.warning("当前环境不支持复制");
      return;
    }
    await navigator.clipboard.writeText(summaryMarkdown);
    message.success("摘要已复制");
  };

  const handleRoleExpandChange = (keys: string | string[]) => {
    const nextKeys = Array.isArray(keys) ? keys : [keys];
    setExpandedRoles(nextKeys);
  };

  const focusRoleGroup = (roleKey: ClarificationRoleKey) => {
    setExpandedRoles((current) => (current.includes(roleKey) ? current : [...current, roleKey]));
  };

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        追问分析
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: -8 }}>
        用于老项目规则不完整时的追问梳理，不接入项目/需求上下文，直接按自由输入分析。
      </Typography.Paragraph>

      <Row gutter={16} align="top">
        <Col span={5}>
          <Card title="最近记录" extra={<Button size="small" onClick={() => void loadRecords()} loading={historyLoading}>刷新</Button>}>
            {historyLoading && records.length === 0 ? (
              <Spin style={{ display: "block", padding: 24 }} />
            ) : records.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无记录" />
            ) : (
              <List
                dataSource={records}
                renderItem={(item) => (
                  <List.Item
                    key={item.id}
                    style={{
                      cursor: "pointer",
                      paddingInline: 8,
                      borderRadius: 8,
                      background: activeRecord?.id === item.id ? "#f0f7ff" : undefined,
                    }}
                    onClick={() => void loadRecordDetail(item.id)}
                  >
                    <Space direction="vertical" size={2} style={{ width: "100%" }}>
                      <Space wrap style={{ justifyContent: "space-between", width: "100%" }}>
                        <Space wrap size={4}>
                          <Typography.Text strong>{`#${item.id}`}</Typography.Text>
                          <Tag color={item.llm_status === "success" ? "blue" : "red"}>{item.llm_status}</Tag>
                          <ProviderTag provider={item.llm_provider} />
                        </Space>
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(item.id);
                          }}
                        />
                      </Space>
                      <Typography.Text ellipsis={{ tooltip: item.requirement_text_preview || "（无需求原文）" }}>
                        {item.requirement_text_preview || "（无需求原文）"}
                      </Typography.Text>
                      <Typography.Text type="secondary">{toDateTimeText(item.created_at)}</Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        <Col span={9}>
          <Card
            title="输入信息"
            extra={
              <Space>
                <Button
                  onClick={() =>
                    form.setFieldValue("rule_text", DEFAULT_RULE_TEXT)
                  }
                >
                  恢复默认规则
                </Button>
                <Button type="primary" loading={submitting} onClick={() => void handleSubmit()}>
                  开始分析
                </Button>
              </Space>
            }
          >
            <Form layout="vertical" form={form}>
              <Form.Item name="requirement_text" label="需求原文">
                <TextArea rows={4} placeholder="贴入原始需求描述" />
              </Form.Item>
              <Form.Item name="current_surface_flow" label="当前表面流程">
                <TextArea rows={3} placeholder="描述目前能看到的表面流程" />
              </Form.Item>
              <Form.Item name="involved_modules" label="涉及模块">
                <TextArea rows={2} placeholder="例如：审批中心、配置平台、消息通知" />
              </Form.Item>
              <Form.Item name="known_background" label="已知背景">
                <TextArea rows={3} placeholder="补充历史背景、上下游约束、遗留实现等" />
              </Form.Item>
              <Form.Item name="unknowns" label="我暂时不知道的内容">
                <TextArea rows={3} placeholder="列出缺失的规则、流程、配置、角色信息" />
              </Form.Item>
              <Form.Item
                name="rule_text"
                label="分析规则"
                rules={[{ required: true, message: "请输入分析规则" }]}
              >
                <TextArea rows={15} placeholder="可编辑默认规则模板" />
              </Form.Item>
            </Form>
          </Card>
        </Col>

        <Col span={10}>
          <Card
            title="分析结果"
            extra={
              activeRecord ? (
                <Space wrap>
                  <Tag color={activeRecord.llm_status === "success" ? "blue" : "red"}>
                    {activeRecord.llm_status === "success" ? "分析成功" : "分析失败"}
                  </Tag>
                  <ProviderTag provider={activeRecord.llm_provider} />
                  <Typography.Text type="secondary">{toDateTimeText(activeRecord.created_at)}</Typography.Text>
                </Space>
              ) : null
            }
          >
            {detailLoading ? (
              <Spin style={{ display: "block", padding: 32 }} />
            ) : !activeRecord ? (
              <Empty description="提交分析后在此查看结构化结果" />
            ) : (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                {activeRecord.llm_status === "failed" ? (
                  <Alert
                    type="warning"
                    showIcon
                    message="模型调用失败"
                    description={activeRecord.llm_message || "未生成有效结果，已保存失败记录。"}
                  />
                ) : null}

                <RuleLikeList
                  title="推测的历史规则与隐含约束"
                  emptyText="暂无识别结果"
                  themeKey="history"
                  items={activeRecord.result.likely_historical_rules}
                  getTitle={(item) => item.rule || "-"}
                  getMetaFields={(item) => [
                    { label: "判断依据", value: item.reason || "-" },
                  ]}
                />

                <RuleLikeList
                  title="关键缺失规则"
                  emptyText="暂无缺失规则"
                  themeKey="missing"
                  items={activeRecord.result.missing_critical_rules}
                  getTitle={(item) => item.rule || "-"}
                  getMetaFields={(item) => [
                    { label: "缺失原因", value: item.why_missing || "-" },
                    { label: "影响", value: item.impact || "-" },
                  ]}
                />

                <Typography.Title level={5} style={{ margin: "4px 0 0" }}>
                  必须优先确认的问题清单
                </Typography.Title>
                <Typography.Paragraph type="secondary" style={{ marginTop: -4, marginBottom: 0 }}>
                  先按角色看全局，再展开查看每个问题的原因和风险。
                </Typography.Paragraph>

                <Row gutter={[12, 12]}>
                  {questionGroups.map((group) => {
                    const isExpanded = expandedRoles.includes(group.roleKey);
                    return (
                      <Col span={12} key={group.roleKey}>
                        <Card
                          size="small"
                          hoverable
                          onClick={() => focusRoleGroup(group.roleKey)}
                          bodyStyle={{ padding: 14 }}
                          style={{
                            borderRadius: 16,
                            cursor: "pointer",
                            background: group.softColor,
                            borderColor: isExpanded ? group.color : group.borderColor,
                            boxShadow: isExpanded
                              ? `0 14px 28px ${group.color}1f`
                              : "0 8px 20px rgba(17, 43, 68, 0.05)",
                          }}
                        >
                          <Space direction="vertical" size={8} style={{ width: "100%" }}>
                            <Space align="center" style={{ justifyContent: "space-between", width: "100%" }}>
                              <Space size={8}>
                                <div
                                  style={{
                                    width: 34,
                                    height: 34,
                                    borderRadius: 12,
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    color: group.color,
                                    background: "#ffffff",
                                    border: `1px solid ${group.borderColor}`,
                                  }}
                                >
                                  {group.icon}
                                </div>
                                <div>
                                  <Space size={6} wrap>
                                    <Typography.Text strong>{group.shortTitle}</Typography.Text>
                                    {group.isExtra ? <Tag color="gold">AI 补充</Tag> : null}
                                  </Space>
                                  <div>
                                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                      {group.helper}
                                    </Typography.Text>
                                  </div>
                                </div>
                              </Space>
                              <Tag
                                style={{
                                  marginInlineEnd: 0,
                                  borderRadius: 999,
                                  color: group.color,
                                  borderColor: `${group.color}30`,
                                  background: "#ffffff",
                                }}
                              >
                                {`${group.items.length} 个问题`}
                              </Tag>
                            </Space>
                            <Typography.Text style={{ color: group.color, fontSize: 12 }}>
                              {isExpanded ? "已展开" : "点击展开该角色问题"}
                            </Typography.Text>
                          </Space>
                        </Card>
                      </Col>
                    );
                  })}
                </Row>

                <Collapse
                  activeKey={expandedRoles}
                  onChange={handleRoleExpandChange}
                  size="large"
                  style={{ background: "transparent" }}
                  items={questionGroups.map((group) => ({
                    key: group.roleKey,
                    label: (
                      <Space size={12} align="center">
                        <div
                          style={{
                            width: 36,
                            height: 36,
                            borderRadius: 12,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            color: group.color,
                            background: group.softColor,
                            border: `1px solid ${group.borderColor}`,
                          }}
                        >
                          {group.icon}
                        </div>
                        <div>
                          <Space size={6} wrap>
                            <Typography.Text strong style={{ fontSize: 16 }}>
                              {group.title}
                            </Typography.Text>
                            {group.isExtra ? <Tag color="gold">AI 补充</Tag> : null}
                          </Space>
                          <div>
                            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                              {group.helper}
                            </Typography.Text>
                          </div>
                        </div>
                        <Tag
                          style={{
                            marginInlineStart: 8,
                            borderRadius: 999,
                            color: group.color,
                            borderColor: `${group.color}30`,
                            background: group.softColor,
                          }}
                        >
                          {`${group.items.length} 个问题`}
                        </Tag>
                      </Space>
                    ),
                    style: {
                      marginBottom: 12,
                      borderRadius: 18,
                      borderColor: group.borderColor,
                      background: "#ffffff",
                    },
                    children: <RoleQuestionSection group={group} />,
                  }))}
                />

                <RuleLikeList
                  title="目前已识别的需求缺陷"
                  emptyText="暂无缺陷"
                  themeKey="gap"
                  items={activeRecord.result.known_requirement_gaps}
                  getTitle={(item) => item.gap || "-"}
                  getMetaFields={(item) => [
                    { label: "原因", value: item.reason || "-" },
                    { label: "影响", value: item.impact || "-" },
                  ]}
                />

                <RuleLikeList
                  title="风险假设"
                  emptyText="暂无风险假设"
                  themeKey="assumption"
                  items={activeRecord.result.risk_assumptions}
                  getTitle={(item) => item.assumption || "-"}
                  getMetaFields={(item) => [
                    { label: "依据", value: item.basis || "-" },
                    { label: "风险", value: item.risk || "-" },
                  ]}
                />

                <Card
                  size="small"
                  title="摘要 Markdown"
                  extra={<Button size="small" onClick={() => void copySummary()}>复制</Button>}
                >
                  {summaryMarkdown.trim() ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{summaryMarkdown}</ReactMarkdown>
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无摘要" />
                  )}
                </Card>
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
