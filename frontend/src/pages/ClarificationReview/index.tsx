import { useEffect, useMemo, useRef, useState } from "react";
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
  DownloadOutlined,
  FilePdfOutlined,
  ShopOutlined,
  TeamOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  analyzeClarificationReview,
  createClarificationReviewPdfDraft,
  deleteClarificationReviewRecord,
  fetchClarificationReviewRecord,
  fetchClarificationReviewRecords,
  inferClarificationReviewPdfDraft,
} from "../../api/clarificationReview";
import { getErrorMessage } from "../../api/client";
import {
  buildExportFileName,
  buildExportMarkdown,
  downloadMarkdown,
  formatGapType,
  getClarificationRoleDescriptors,
  isClarificationReviewResultV2,
} from "./exportMarkdown";
import type {
  ClarificationReviewAnalyzeRequest,
  ClarificationReviewPdfDraft,
  ClarificationReviewPdfField,
  ClarificationReviewPdfResult,
  ClarificationReviewQuestionItem,
  ClarificationReviewRecord,
  ClarificationReviewRecordSummary,
  ClarificationReviewSourceMeta,
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

type PdfFieldKey =
  | "requirement_text"
  | "current_surface_flow"
  | "involved_modules"
  | "known_background"
  | "unknowns";

type DraftApplyMode = "keep" | "replace" | "append";

const PDF_FIELD_META: Record<PdfFieldKey, { label: string }> = {
  requirement_text: { label: "需求原文" },
  current_surface_flow: { label: "当前表面流程" },
  involved_modules: { label: "涉及模块" },
  known_background: { label: "已知背景" },
  unknowns: { label: "我暂时不知道的内容" },
};

const PDF_FIELD_KEYS = Object.keys(PDF_FIELD_META) as PdfFieldKey[];

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

function DraftStatusTag({ status }: { status: ClarificationReviewPdfDraft["status"] }) {
  const color =
    status === "success"
      ? "green"
      : status === "partial_success"
        ? "gold"
        : status === "failed"
          ? "red"
          : "blue";
  return <Tag color={color}>{status}</Tag>;
}

function SourceMetaTag({ sourceMeta }: { sourceMeta: ClarificationReviewSourceMeta | null }) {
  if (!sourceMeta) return <Tag>手填</Tag>;
  return <Tag color={sourceMeta.draft_expired ? "gold" : "blue"}>{sourceMeta.draft_expired ? "PDF 导入(已过期)" : "PDF 导入"}</Tag>;
}

function getDraftResultToApply(draft: ClarificationReviewPdfDraft | null): ClarificationReviewPdfResult | null {
  if (!draft) return null;
  return draft.inference_result || draft.strict_result;
}

function normalizeFieldValue(field: ClarificationReviewPdfField | undefined): ClarificationReviewPdfField {
  return {
    value: String(field?.value || ""),
    evidence: String(field?.evidence || ""),
  };
}

function PdfResultBlock({
  title,
  result,
  accentColor,
}: {
  title: string;
  result: ClarificationReviewPdfResult | null;
  accentColor: string;
}) {
  return (
    <Card
      size="small"
      title={title}
      style={{ borderRadius: 16, borderColor: `${accentColor}33` }}
      bodyStyle={{ padding: 16 }}
    >
      {!result ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无结果" />
      ) : (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {PDF_FIELD_KEYS.map((fieldKey) => {
            const field = normalizeFieldValue(result.fields[fieldKey]);
            return (
              <div
                key={fieldKey}
                style={{
                  border: `1px solid ${accentColor}22`,
                  borderRadius: 12,
                  padding: 12,
                  background: `${accentColor}08`,
                }}
              >
                <Typography.Text strong>{PDF_FIELD_META[fieldKey].label}</Typography.Text>
                <Typography.Paragraph style={{ marginTop: 8, marginBottom: 8, whiteSpace: "pre-wrap" }}>
                  {field.value || "未提取到内容"}
                </Typography.Paragraph>
                {hasMeaningfulText(field.evidence) ? (
                  <Typography.Text type="secondary">{`证据：${field.evidence}`}</Typography.Text>
                ) : null}
              </div>
            );
          })}
          {result.conflicts.length > 0 ? (
            <Alert
              type="warning"
              showIcon
              message="检测到文档冲突"
              description={
                <Space direction="vertical" size={8}>
                  {result.conflicts.map((item, index) => (
                    <div key={`${item.field}-${index}`}>
                      <Typography.Text strong>{item.description}</Typography.Text>
                      <div>
                        <Typography.Text type="secondary">{`${item.field} · ${item.evidence || "无证据说明"}`}</Typography.Text>
                      </div>
                    </div>
                  ))}
                </Space>
              }
            />
          ) : null}
        </Space>
      )}
    </Card>
  );
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
                <QuestionMetaRow label="必须产出" value={item.required_output || ""} accentColor={meta.color} />
                <QuestionMetaRow label="答案形式" value={formatAnswerFormatLabel(item.answer_format)} accentColor={meta.color} />
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

const GAP_PRIORITY_META = {
  P0: { title: "P0 阻塞级缺陷", emptyText: "当前未发现阻塞级缺陷", themeKey: "gap" },
  P1: { title: "P1 高风险缺陷", emptyText: "当前未发现高风险缺陷", themeKey: "missing" },
  P2: { title: "P2 补充级缺陷", emptyText: "当前未发现补充级缺陷", themeKey: "history" },
} as const;
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

function formatAnswerFormatLabel(value: string | undefined): string {
  if (value === "table") return "表格";
  if (value === "flow") return "流程";
  return "文本";
}

function formatSourceTypeLabel(value: string | undefined): string {
  if (value === "input_text") return "输入信息";
  if (value === "pdf_draft") return "PDF 草稿";
  return "模型推断";
}

export default function ClarificationReviewPage() {
  const [form] = Form.useForm<ClarificationReviewFormValues>();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [draftLoading, setDraftLoading] = useState(false);
  const [inferLoading, setInferLoading] = useState(false);
  const [activeDraftId, setActiveDraftId] = useState<number | null>(null);
  const [activeDraft, setActiveDraft] = useState<ClarificationReviewPdfDraft | null>(null);
  const [applyModalOpen, setApplyModalOpen] = useState(false);
  const [draftApplyModes, setDraftApplyModes] = useState<Partial<Record<PdfFieldKey, DraftApplyMode>>>({});
  const [draftAppliedSnapshot, setDraftAppliedSnapshot] = useState<Partial<Record<PdfFieldKey, string>>>({});
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

  const resetDraftState = () => {
    setActiveDraftId(null);
    setActiveDraft(null);
    setDraftAppliedSnapshot({});
    setDraftApplyModes({});
    setApplyModalOpen(false);
  };

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
      resetDraftState();
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
            setHistoryLoading(true);
            try {
              const data = await fetchClarificationReviewRecords(20);
              setRecords(data);
            } finally {
              setHistoryLoading(false);
            }
          } else {
            await loadRecords();
          }
        } catch (error) {
          message.error(getErrorMessage(error, "删除失败"));
        }
      },
    });
  };

  const requestReplaceDraft = async (): Promise<boolean> =>
    new Promise((resolve) => {
      Modal.confirm({
        title: "替换当前 PDF 草稿",
        content: "当前已有一份 PDF 草稿，继续导入会替换它。是否继续？",
        okText: "替换",
        cancelText: "取消",
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      });
    });

  const handleImportPdf = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      message.warning("仅支持上传 PDF 文件");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      message.warning("PDF 体积不能超过 20MB");
      return;
    }
    if (activeDraftId) {
      const confirmed = await requestReplaceDraft();
      if (!confirmed) return;
    }

    setDraftLoading(true);
    try {
      const draft = await createClarificationReviewPdfDraft(file);
      setActiveDraftId(draft.id);
      setActiveDraft(draft);
      setDraftAppliedSnapshot({});
      setDraftApplyModes({});
      message.success("PDF 草稿已生成");
    } catch (error) {
      message.error(getErrorMessage(error, "PDF 导入失败"));
    } finally {
      setDraftLoading(false);
    }
  };

  const handleOpenApplyModal = () => {
    const result = getDraftResultToApply(activeDraft);
    if (!result) {
      message.warning("当前没有可应用的草稿内容");
      return;
    }

    const currentValues = form.getFieldsValue();
    const nextModes: Partial<Record<PdfFieldKey, DraftApplyMode>> = {};
    PDF_FIELD_KEYS.forEach((fieldKey) => {
      const currentValue = String(currentValues[fieldKey] || "").trim();
      const draftValue = normalizeFieldValue(result.fields[fieldKey]).value.trim();
      if (!currentValue && !draftValue) return;
      nextModes[fieldKey] = !currentValue && draftValue ? "replace" : "keep";
    });
    setDraftApplyModes(nextModes);
    setApplyModalOpen(true);
  };

  const handleApplyDraftToForm = () => {
    const result = getDraftResultToApply(activeDraft);
    if (!result) return;

    const currentValues = form.getFieldsValue();
    const nextValues: Partial<ClarificationReviewFormValues> = {};
    const snapshot: Partial<Record<PdfFieldKey, string>> = {};

    PDF_FIELD_KEYS.forEach((fieldKey) => {
      const mode = draftApplyModes[fieldKey] || "keep";
      const currentValue = String(currentValues[fieldKey] || "").trim();
      const draftValue = normalizeFieldValue(result.fields[fieldKey]).value.trim();
      if (!draftValue || mode === "keep") return;

      const mergedValue = mode === "append" && currentValue ? `${currentValue}\n${draftValue}` : draftValue;
      nextValues[fieldKey] = mergedValue;
      snapshot[fieldKey] = mergedValue;
    });

    form.setFieldsValue(nextValues);
    setDraftAppliedSnapshot(snapshot);
    setApplyModalOpen(false);
    message.success("草稿内容已回填到表单");
  };

  const handleInferDraft = async () => {
    if (!activeDraftId) return;
    setInferLoading(true);
    try {
      const draft = await inferClarificationReviewPdfDraft(activeDraftId);
      setActiveDraft(draft);
      message.success("补充推断已更新");
    } catch (error) {
      message.error(getErrorMessage(error, "补充推断失败"));
    } finally {
      setInferLoading(false);
    }
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
      const appliedFields = PDF_FIELD_KEYS.filter((fieldKey) => {
        const snapshotValue = draftAppliedSnapshot[fieldKey];
        if (!snapshotValue) return false;
        return String(values[fieldKey] || "").trim() === snapshotValue.trim();
      });
      const record = await analyzeClarificationReview({
        requirement_text: values.requirement_text.trim(),
        current_surface_flow: values.current_surface_flow.trim(),
        involved_modules: values.involved_modules.trim(),
        known_background: values.known_background.trim(),
        unknowns: values.unknowns.trim(),
        rule_text: values.rule_text.trim(),
        source_draft_id: activeDraftId || undefined,
        applied_fields: appliedFields,
      });
      setActiveRecord(record);
      resetDraftState();
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
  const isResultV2 = useMemo(() => isClarificationReviewResultV2(activeRecord), [activeRecord]);
  const questionGroups = useMemo(
    () =>
      getClarificationRoleDescriptors(activeRecord).map((descriptor, index) => ({
        roleKey: descriptor.key,
        ...getRoleMeta(descriptor.key, index),
        items: activeRecord?.result.priority_questions_by_role[descriptor.key] || [],
        source: descriptor.source,
        isExtra: descriptor.source === "llm_extra",
      })),
    [activeRecord],
  );
  const groupedV2Gaps = useMemo(
    () => ({
      P0: activeRecord?.result.known_requirement_gaps.filter((item) => item.priority === "P0") || [],
      P1: activeRecord?.result.known_requirement_gaps.filter((item) => item.priority === "P1") || [],
      P2:
        activeRecord?.result.known_requirement_gaps.filter((item) => !item.priority || item.priority === "P2") || [],
    }),
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

  const handleExportMarkdown = () => {
    if (!activeRecord || activeRecord.llm_status !== "success") {
      message.warning("暂无可导出的分析结果");
      return;
    }

    try {
      const content = buildExportMarkdown(activeRecord);
      const fileName = buildExportFileName(activeRecord);
      downloadMarkdown(fileName, content);
      message.success("Markdown 已开始下载");
    } catch (error) {
      message.error(getErrorMessage(error, "导出 Markdown 失败"));
    }
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
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,application/pdf"
        style={{ display: "none" }}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            void handleImportPdf(file);
          }
          event.target.value = "";
        }}
      />
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
                          <SourceMetaTag sourceMeta={item.source_meta} />
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
                  icon={<UploadOutlined />}
                  loading={draftLoading}
                  onClick={() => fileInputRef.current?.click()}
                >
                  导入 PDF
                </Button>
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

            {activeDraft ? (
              <Card
                size="small"
                title={
                  <Space wrap>
                    <FilePdfOutlined />
                    <Typography.Text strong>PDF 拆解草稿</Typography.Text>
                    <DraftStatusTag status={activeDraft.status} />
                    <ProviderTag provider={activeDraft.llm_provider} />
                  </Space>
                }
                extra={
                  <Space wrap>
                    {(activeDraft.status === "success" || activeDraft.status === "partial_success") ? (
                      <Button onClick={() => void handleInferDraft()} loading={inferLoading}>
                        LLM 补充推断
                      </Button>
                    ) : null}
                    <Button type="primary" onClick={handleOpenApplyModal}>
                      应用到表单
                    </Button>
                  </Space>
                }
                style={{ borderRadius: 16 }}
                bodyStyle={{ padding: 16 }}
              >
                <Space direction="vertical" size={12} style={{ width: "100%" }}>
                  <Space wrap>
                    <Typography.Text>{activeDraft.file_name}</Typography.Text>
                    <Typography.Text type="secondary">{`${activeDraft.page_count} 页`}</Typography.Text>
                    <Typography.Text type="secondary">{toDateTimeText(activeDraft.created_at)}</Typography.Text>
                  </Space>
                  {activeDraft.llm_message ? (
                    <Alert type="warning" showIcon message={activeDraft.llm_message} />
                  ) : null}
                  <PdfResultBlock title="严格提取" result={activeDraft.strict_result} accentColor="#1d4ed8" />
                  {activeDraft.inference_result ? (
                    <PdfResultBlock title="推断补充" result={activeDraft.inference_result} accentColor="#0f766e" />
                  ) : null}
                  {Object.keys(draftAppliedSnapshot).length > 0 ? (
                    <Typography.Text type="secondary">
                      {`已应用字段：${Object.keys(draftAppliedSnapshot).map((key) => PDF_FIELD_META[key as PdfFieldKey].label).join("、")}`}
                    </Typography.Text>
                  ) : null}
                </Space>
              </Card>
            ) : null}
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
                  {activeRecord.llm_status === "success" ? (
                    <Button size="small" icon={<DownloadOutlined />} onClick={handleExportMarkdown}>
                      导出
                    </Button>
                  ) : null}
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

                {activeRecord.source_meta ? (
                  <Alert
                    type="info"
                    showIcon
                    message={activeRecord.source_meta.draft_expired ? "本次分析来源于已过期的 PDF 草稿" : "本次分析来源于 PDF 草稿"}
                    description={`应用字段：${activeRecord.source_meta.applied_fields.length > 0 ? activeRecord.source_meta.applied_fields.map((field) => PDF_FIELD_META[field as PdfFieldKey]?.label || field).join("、") : "无"}`}
                  />
                ) : null}
                {isResultV2 ? (
                  <>
                    <RuleLikeList
                      title="合理推断"
                      emptyText="暂无合理推断"
                      themeKey="history"
                      items={activeRecord.result.inferred_items || []}
                      getTitle={(item) => item.statement || "-"}
                      getMetaFields={(item) => [
                        { label: "依据", value: item.evidence || "-" },
                        { label: "来源", value: formatSourceTypeLabel(item.source_type) },
                      ]}
                    />

                    <RuleLikeList
                      title="风险假设"
                      emptyText="暂无风险假设"
                      themeKey="assumption"
                      items={activeRecord.result.assumption_items || []}
                      getTitle={(item) => item.assumption || "-"}
                      getMetaFields={(item) => [
                        { label: "依据", value: item.basis || "-" },
                        { label: "风险", value: item.risk || "-" },
                      ]}
                    />
                  </>
                ) : (
                  <>
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
                  </>
                )}

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

                {isResultV2 ? (
                  <>
                    <RuleLikeList
                      title={GAP_PRIORITY_META.P0.title}
                      emptyText={GAP_PRIORITY_META.P0.emptyText}
                      themeKey={GAP_PRIORITY_META.P0.themeKey}
                      items={groupedV2Gaps.P0}
                      getTitle={(item) => item.gap || "-"}
                      getMetaFields={(item) => [
                        { label: "类型", value: formatGapType(item.gap_type) },
                        { label: "原因", value: item.reason || "-" },
                        { label: "影响", value: item.impact || "-" },
                        { label: "阻塞说明", value: item.blocking_reason || "-" },
                      ]}
                    />

                    <RuleLikeList
                      title={GAP_PRIORITY_META.P1.title}
                      emptyText={GAP_PRIORITY_META.P1.emptyText}
                      themeKey={GAP_PRIORITY_META.P1.themeKey}
                      items={groupedV2Gaps.P1}
                      getTitle={(item) => item.gap || "-"}
                      getMetaFields={(item) => [
                        { label: "类型", value: formatGapType(item.gap_type) },
                        { label: "原因", value: item.reason || "-" },
                        { label: "影响", value: item.impact || "-" },
                      ]}
                    />

                    <RuleLikeList
                      title={GAP_PRIORITY_META.P2.title}
                      emptyText={GAP_PRIORITY_META.P2.emptyText}
                      themeKey={GAP_PRIORITY_META.P2.themeKey}
                      items={groupedV2Gaps.P2}
                      getTitle={(item) => item.gap || "-"}
                      getMetaFields={(item) => [
                        { label: "类型", value: formatGapType(item.gap_type) },
                        { label: "原因", value: item.reason || "-" },
                        { label: "影响", value: item.impact || "-" },
                      ]}
                    />
                  </>
                ) : (
                  <>
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
                  </>
                )}

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

      <Modal
        title="选择如何应用 PDF 草稿"
        open={applyModalOpen}
        onOk={handleApplyDraftToForm}
        onCancel={() => setApplyModalOpen(false)}
        okText="确认应用"
        cancelText="取消"
        width={860}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {PDF_FIELD_KEYS.map((fieldKey) => {
            const result = getDraftResultToApply(activeDraft);
            const draftField = normalizeFieldValue(result?.fields[fieldKey]);
            const currentValue = String(form.getFieldValue(fieldKey) || "").trim();
            if (!currentValue && !draftField.value.trim()) return null;
            return (
              <Card key={fieldKey} size="small" style={{ borderRadius: 12 }}>
                <Space direction="vertical" size={8} style={{ width: "100%" }}>
                  <Space wrap style={{ justifyContent: "space-between", width: "100%" }}>
                    <Typography.Text strong>{PDF_FIELD_META[fieldKey].label}</Typography.Text>
                    <select
                      value={draftApplyModes[fieldKey] || "keep"}
                      onChange={(event) =>
                        setDraftApplyModes((current) => ({
                          ...current,
                          [fieldKey]: event.target.value as DraftApplyMode,
                        }))
                      }
                      style={{ padding: "6px 8px", borderRadius: 8, borderColor: "#d9d9d9" }}
                    >
                      <option value="keep">保留当前</option>
                      <option value="replace">使用 PDF</option>
                      <option value="append">追加合并</option>
                    </select>
                  </Space>
                  <div>
                    <Typography.Text type="secondary">当前值</Typography.Text>
                    <Typography.Paragraph style={{ marginBottom: 8, whiteSpace: "pre-wrap" }}>
                      {currentValue || "空"}
                    </Typography.Paragraph>
                  </div>
                  <div>
                    <Typography.Text type="secondary">PDF 值</Typography.Text>
                    <Typography.Paragraph style={{ marginBottom: 4, whiteSpace: "pre-wrap" }}>
                      {draftField.value || "空"}
                    </Typography.Paragraph>
                    {hasMeaningfulText(draftField.evidence) ? (
                      <Typography.Text type="secondary">{`证据：${draftField.evidence}`}</Typography.Text>
                    ) : null}
                  </div>
                </Space>
              </Card>
            );
          })}
        </Space>
      </Modal>
    </div>
  );
}
