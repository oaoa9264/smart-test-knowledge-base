import type {
  ClarificationReviewGapItem,
  ClarificationReviewQuestionItem,
  ClarificationReviewRecord,
  ClarificationReviewRoleDescriptorItem,
} from "../../types";

function hasMeaningfulText(value: string | null | undefined): boolean {
  const normalized = String(value || "").trim();
  return Boolean(normalized && normalized !== "-");
}

function toDateText(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知日期";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function toDateTimeText(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function normalizePlainText(value: string | null | undefined): string {
  return hasMeaningfulText(value) ? String(value).trim() : "暂无";
}

function escapeMarkdownTableCell(value: string | null | undefined): string {
  const normalized = normalizePlainText(value);
  return normalized
    .replace(/\\/g, "\\\\")
    .replace(/\|/g, "\\|")
    .replace(/`/g, "\\`")
    .replace(/\r?\n/g, "<br/>");
}

function buildMarkdownTable(headers: string[], rows: string[][]): string {
  const headerLine = `| ${headers.join(" | ")} |`;
  const dividerLine = `| ${headers.map(() => "---").join(" | ")} |`;
  const rowLines = rows.map((row) => `| ${row.join(" | ")} |`);
  return [headerLine, dividerLine, ...rowLines].join("\n");
}

function buildMultilineSection(title: string, value: string | null | undefined): string {
  const normalized = normalizePlainText(value);
  const formatted = normalized === "暂无" ? normalized : normalized.replace(/\r?\n/g, "  \n");
  return [`### ${title}`, formatted].join("\n\n");
}

function buildTableSection(title: string, headers: string[], rows: string[][], emptyText: string): string {
  return [`## ${title}`, rows.length > 0 ? buildMarkdownTable(headers, rows) : emptyText].join("\n\n");
}

function formatAnswerFormat(value: string | undefined): string {
  if (value === "table") return "表格";
  if (value === "flow") return "流程";
  return "文本";
}

function formatSourceType(value: string): string {
  if (value === "input_text") return "输入信息";
  if (value === "pdf_draft") return "PDF 草稿";
  return "模型推断";
}

export function formatResolutionStatus(value: string | null | undefined): string {
  const normalized = String(value || "").trim();
  if (normalized === "confirmed") return "已确认";
  if (normalized === "assume_and_proceed") return "按假设推进";
  if (normalized === "dismissed") return "已忽略";
  return "待处理";
}

function formatResolvedInfo(resolvedBy: string | null | undefined, resolvedAt: string | null | undefined): string {
  const who = String(resolvedBy || "").trim();
  const when = String(resolvedAt || "").trim();
  if (!who && !when) return "-";
  if (who && when) return `${who} · ${toDateTimeText(when)}`;
  return who || toDateTimeText(when);
}

export function formatGapType(value: string | undefined): string {
  if (value === "rule_missing") return "规则缺失";
  if (value === "process_gap") return "流程缺失";
  if (value === "boundary_undefined") return "边界未定义";
  if (value === "data_missing") return "数据缺失";
  return "逻辑缺口";
}

function groupGapsByPriority(items: ClarificationReviewGapItem[]) {
  return {
    P0: items.filter((item) => item.priority === "P0"),
    P1: items.filter((item) => item.priority === "P1"),
    P2: items.filter((item) => item.priority === "P2" || !item.priority),
  };
}

function getRoleExportTitle(roleKey: string): string {
  return `${roleKey}需要确认`;
}

export function isClarificationReviewResultV2(record: ClarificationReviewRecord | null): boolean {
  return record?.result?.result_version === 2;
}

export function getClarificationRoleDescriptors(
  record: ClarificationReviewRecord | null,
): ClarificationReviewRoleDescriptorItem[] {
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

export function buildExportFileName(record: ClarificationReviewRecord): string {
  return `追问分析_${record.id}_${toDateText(record.created_at)}.md`;
}

export function buildExportMarkdown(record: ClarificationReviewRecord): string {
  if (isClarificationReviewResultV2(record)) {
    return buildExportMarkdownV2(record);
  }
  return buildExportMarkdownLegacy(record);
}

function buildQuestionSection(
  roleDescriptors: ClarificationReviewRoleDescriptorItem[],
  priorityQuestionsByRole: Record<string, ClarificationReviewQuestionItem[]>,
) {
  const roleSections = roleDescriptors.map((descriptor) => {
    const items = priorityQuestionsByRole[descriptor.key] || [];
    const title = descriptor.source === "llm_extra"
      ? `${getRoleExportTitle(descriptor.key)}（AI 补充）`
      : getRoleExportTitle(descriptor.key);

    return [
      `### ${title}`,
      items.length > 0
        ? buildMarkdownTable(
            ["问题", "必须产出", "答案形式", "为什么要问", "不问的风险", "处理状态", "处理备注", "处理人/时间"],
            items.map((item) => [
              escapeMarkdownTableCell(item.question),
              escapeMarkdownTableCell(item.required_output || "暂无"),
              escapeMarkdownTableCell(formatAnswerFormat(item.answer_format)),
              escapeMarkdownTableCell(item.why_ask),
              escapeMarkdownTableCell(item.risk_if_unasked),
              escapeMarkdownTableCell(formatResolutionStatus((item as ClarificationReviewQuestionItem & { resolution_status?: string }).resolution_status)),
              escapeMarkdownTableCell((item as ClarificationReviewQuestionItem & { resolution_note?: string }).resolution_note || "-"),
              escapeMarkdownTableCell(formatResolvedInfo(
                (item as ClarificationReviewQuestionItem & { resolved_by?: string }).resolved_by,
                (item as ClarificationReviewQuestionItem & { resolved_at?: string }).resolved_at,
              )),
            ]),
          )
        : "暂无",
    ].join("\n\n");
  });

  return ["## 必须补齐的规则答案", roleSections.length > 0 ? roleSections.join("\n\n") : "暂无"].join("\n\n");
}

function buildGapPrioritySection(title: string, items: ClarificationReviewGapItem[], emptyText: string): string {
  return [
    `## ${title}`,
    items.length > 0
        ? buildMarkdownTable(
            ["缺陷", "类型", "原因", "影响", "阻塞说明", "处理状态", "处理备注", "处理人/时间"],
            items.map((item) => [
              escapeMarkdownTableCell(item.gap),
              escapeMarkdownTableCell(formatGapType(item.gap_type)),
              escapeMarkdownTableCell(item.reason),
              escapeMarkdownTableCell(item.impact),
              escapeMarkdownTableCell(item.blocking_reason || "暂无"),
              escapeMarkdownTableCell(formatResolutionStatus((item as ClarificationReviewGapItem & { resolution_status?: string }).resolution_status)),
              escapeMarkdownTableCell((item as ClarificationReviewGapItem & { resolution_note?: string }).resolution_note || "-"),
              escapeMarkdownTableCell(formatResolvedInfo(
                (item as ClarificationReviewGapItem & { resolved_by?: string }).resolved_by,
                (item as ClarificationReviewGapItem & { resolved_at?: string }).resolved_at,
              )),
            ]),
          )
      : emptyText,
  ].join("\n\n");
}

function buildExportMarkdownV2(record: ClarificationReviewRecord): string {
  const roleDescriptors = getClarificationRoleDescriptors(record);
  const groupedGaps = groupGapsByPriority(record.result.known_requirement_gaps || []);
  const sections: string[] = [
    `# 追问分析评审结论 #${record.id}`,
    [
      "## 标题与元信息",
      `- 记录 ID：#${record.id}`,
      `- 分析时间：${toDateTimeText(record.created_at)}`,
      `- 模型状态：${normalizePlainText(record.llm_status)}`,
      `- 模型提供商：${normalizePlainText(record.llm_provider)}`,
    ].join("\n"),
    [
      "## 输入信息",
      buildMultilineSection("需求原文", record.input_payload.requirement_text),
      buildMultilineSection("当前表面流程", record.input_payload.current_surface_flow),
      buildMultilineSection("涉及模块", record.input_payload.involved_modules),
      buildMultilineSection("已知背景", record.input_payload.known_background),
      buildMultilineSection("未知项", record.input_payload.unknowns),
    ].join("\n\n"),
    `## 分析规则\n\n${normalizePlainText(record.rule_text).replace(/\r?\n/g, "  \n")}`,
    buildTableSection(
      "合理推断",
      ["结论", "依据", "来源"],
      (record.result.inferred_items || []).map((item) => [
        escapeMarkdownTableCell(item.statement),
        escapeMarkdownTableCell(item.evidence),
        escapeMarkdownTableCell(formatSourceType(item.source_type)),
      ]),
      "暂无识别结果",
    ),
    buildTableSection(
      "风险假设",
      ["假设", "依据", "风险", "处理状态", "处理备注", "处理人/时间"],
      (record.result.assumption_items || []).map((item) => [
        escapeMarkdownTableCell(item.assumption),
        escapeMarkdownTableCell(item.basis),
        escapeMarkdownTableCell(item.risk),
        escapeMarkdownTableCell(formatResolutionStatus((item as typeof item & { resolution_status?: string }).resolution_status)),
        escapeMarkdownTableCell((item as typeof item & { resolution_note?: string }).resolution_note || "-"),
        escapeMarkdownTableCell(formatResolvedInfo(
          (item as typeof item & { resolved_by?: string }).resolved_by,
          (item as typeof item & { resolved_at?: string }).resolved_at,
        )),
      ]),
      "暂无风险假设",
    ),
    buildQuestionSection(roleDescriptors, record.result.priority_questions_by_role || {}),
    buildGapPrioritySection("P0 缺陷", groupedGaps.P0, "当前未发现阻塞级缺陷"),
    buildGapPrioritySection("P1 缺陷", groupedGaps.P1, "当前未发现高风险缺陷"),
    buildGapPrioritySection("P2 缺陷", groupedGaps.P2, "当前未发现补充级缺陷"),
    `## 摘要\n\n${hasMeaningfulText(record.result.summary_markdown) ? record.result.summary_markdown : "暂无"}`,
  ];

  return `${sections.join("\n\n")}\n`;
}

function buildExportMarkdownLegacy(record: ClarificationReviewRecord): string {
  const roleDescriptors = getClarificationRoleDescriptors(record);
  const sections: string[] = [
    `# 追问分析导出 #${record.id}`,
    [
      "## 标题与元信息",
      `- 记录 ID：#${record.id}`,
      `- 分析时间：${toDateTimeText(record.created_at)}`,
      `- 模型状态：${normalizePlainText(record.llm_status)}`,
      `- 模型提供商：${normalizePlainText(record.llm_provider)}`,
    ].join("\n"),
    [
      "## 输入信息",
      buildMultilineSection("需求原文", record.input_payload.requirement_text),
      buildMultilineSection("当前表面流程", record.input_payload.current_surface_flow),
      buildMultilineSection("涉及模块", record.input_payload.involved_modules),
      buildMultilineSection("已知背景", record.input_payload.known_background),
      buildMultilineSection("未知项", record.input_payload.unknowns),
    ].join("\n\n"),
    `## 分析规则\n\n${normalizePlainText(record.rule_text).replace(/\r?\n/g, "  \n")}`,
    buildTableSection(
      "推测的历史规则",
      ["规则", "判断依据"],
      record.result.likely_historical_rules.map((item) => [
        escapeMarkdownTableCell(item.rule),
        escapeMarkdownTableCell(item.reason),
      ]),
      "暂无识别结果",
    ),
    buildTableSection(
      "关键缺失规则",
      ["规则", "缺失原因", "影响"],
      record.result.missing_critical_rules.map((item) => [
        escapeMarkdownTableCell(item.rule),
        escapeMarkdownTableCell(item.why_missing),
        escapeMarkdownTableCell(item.impact),
      ]),
      "暂无缺失规则",
    ),
    buildQuestionSection(roleDescriptors, record.result.priority_questions_by_role || {}),
    buildTableSection(
      "已识别需求缺陷",
      ["缺陷", "原因", "影响", "处理状态", "处理备注", "处理人/时间"],
      record.result.known_requirement_gaps.map((item) => [
        escapeMarkdownTableCell(item.gap),
        escapeMarkdownTableCell(item.reason),
        escapeMarkdownTableCell(item.impact),
        escapeMarkdownTableCell(formatResolutionStatus((item as typeof item & { resolution_status?: string }).resolution_status)),
        escapeMarkdownTableCell((item as typeof item & { resolution_note?: string }).resolution_note || "-"),
        escapeMarkdownTableCell(formatResolvedInfo(
          (item as typeof item & { resolved_by?: string }).resolved_by,
          (item as typeof item & { resolved_at?: string }).resolved_at,
        )),
      ]),
      "暂无缺陷",
    ),
    buildTableSection(
      "风险假设",
      ["假设", "依据", "风险", "处理状态", "处理备注", "处理人/时间"],
      record.result.risk_assumptions.map((item) => [
        escapeMarkdownTableCell(item.assumption),
        escapeMarkdownTableCell(item.basis),
        escapeMarkdownTableCell(item.risk),
        escapeMarkdownTableCell(formatResolutionStatus((item as typeof item & { resolution_status?: string }).resolution_status)),
        escapeMarkdownTableCell((item as typeof item & { resolution_note?: string }).resolution_note || "-"),
        escapeMarkdownTableCell(formatResolvedInfo(
          (item as typeof item & { resolved_by?: string }).resolved_by,
          (item as typeof item & { resolved_at?: string }).resolved_at,
        )),
      ]),
      "暂无风险假设",
    ),
    `## 摘要\n\n${hasMeaningfulText(record.result.summary_markdown) ? record.result.summary_markdown : "暂无"}`,
  ];

  return `${sections.join("\n\n")}\n`;
}

export function downloadMarkdown(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
