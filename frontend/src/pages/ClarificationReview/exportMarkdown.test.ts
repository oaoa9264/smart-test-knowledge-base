import type { ClarificationReviewRecord } from "../../types";
import { buildExportFileName, buildExportMarkdown } from "./exportMarkdown";

function assertMatch(value: string, pattern: RegExp) {
  if (!pattern.test(value)) {
    throw new Error(`Expected value to match ${pattern}, got:\n${value}`);
  }
}

function assertEqual<T>(actual: T, expected: T) {
  if (actual !== expected) {
    throw new Error(`Expected ${String(expected)}, got ${String(actual)}`);
  }
}

const sampleRecord: ClarificationReviewRecord = {
  id: 42,
  input_payload: {
    requirement_text: "用户提交后，需要通知审批人",
    current_surface_flow: "提交申请\n进入审批",
    involved_modules: "审批中心 | 消息中心",
    known_background: "",
    unknowns: "审批超时后的处理方式",
  },
  rule_text: "1. 必须确认超时规则\n2. 保留原有通知策略",
  result: {
    likely_historical_rules: [
      {
        rule: "通知模板按租户隔离 | 不允许串用",
        reason: "历史系统使用多租户配置\n模板来源不统一",
      },
    ],
    missing_critical_rules: [],
    priority_questions_by_role: {
      产品: [
        {
          question: "审批超时后是否自动通过？",
          why_ask: "直接影响流程分支",
          risk_if_unasked: "可能导致审批卡死",
        },
      ],
      架构: [
        {
          question: "是否存在异步补偿队列？",
          why_ask: "关系到失败重试",
          risk_if_unasked: "通知失败后没有兜底",
        },
      ],
    },
    configured_roles: ["产品"],
    role_descriptors: [{ key: "产品", source: "rule_text" }],
    known_requirement_gaps: [
      {
        gap: "未说明审批超时后的处理动作",
        reason: "需求原文只描述了提交流程",
        impact: "测试无法覆盖超时分支",
      },
    ],
    risk_assumptions: [
      {
        assumption: "沿用老系统的消息通知机制",
        basis: "当前模块仍依赖历史消息中心",
        risk: "新流程可能没有正确接入模板配置",
      },
    ],
    summary_markdown: "## 摘要\n\n- 先确认审批超时规则",
    llm_status: "success",
    llm_provider: "openai",
    llm_message: null,
  },
  llm_status: "success",
  llm_provider: "openai",
  llm_message: null,
  source_meta: null,
  created_at: "2026-04-14T10:20:30.000Z",
};

function testBuildExportMarkdown() {
  const markdown = buildExportMarkdown(sampleRecord);

  assertMatch(markdown, /^# 追问分析导出 #42/m);
  assertMatch(markdown, /## 分析规则/);
  assertMatch(markdown, /1\. 必须确认超时规则/);
  assertMatch(markdown, /\| 通知模板按租户隔离 \\| 不允许串用 \| 历史系统使用多租户配置<br\/>模板来源不统一 \|/);
  assertMatch(markdown, /### 产品需要确认/);
  assertMatch(markdown, /### 架构需要确认（AI 补充）/);
  assertMatch(markdown, /暂无缺失规则/);
  assertMatch(markdown, /## 摘要\n\n## 摘要/);
}

function testBuildExportFileName() {
  const fileName = buildExportFileName(sampleRecord);
  assertEqual(fileName, "追问分析_42_2026-04-14.md");
}

function testBuildExportMarkdownV2() {
  const markdown = buildExportMarkdown({
    ...sampleRecord,
    result: {
      ...sampleRecord.result,
      result_version: 2,
      inferred_items: [
        {
          statement: "审批流可能存在金额阈值分级",
          evidence: "审批中心老项目通常按金额区间走不同审批层级",
          source_type: "input_text",
        },
      ],
      assumption_items: [
        {
          assumption: "驳回后已发通知需要撤回",
          basis: "输入只描述了通过通知，未覆盖驳回场景",
          risk: "若不撤回会出现错误通知",
        },
      ],
      priority_questions_by_role: {
        产品: [
          {
            question: "驳回后通知如何处理？",
            why_ask: "关系到主流程状态一致性",
            risk_if_unasked: "开发无法确定驳回分支处理",
            required_output: "请给出驳回通知处理规则表",
            answer_format: "table",
          },
        ],
      },
      known_requirement_gaps: [
        {
          gap: "驳回后的通知处理规则缺失",
          gap_type: "rule_missing",
          reason: "需求没有定义驳回后已发通知是否撤回",
          impact: "开发和测试无法确认驳回链路",
          priority: "P0",
          blocking_reason: "驳回是主流程分支，不确认通知策略无法实现",
        },
      ],
      likely_historical_rules: [],
      missing_critical_rules: [],
      risk_assumptions: [],
      summary_markdown: "## 摘要\n\n- 先确认驳回通知规则",
    },
  });

  assertMatch(markdown, /## 合理推断/);
  assertMatch(markdown, /## 风险假设/);
  assertMatch(markdown, /## 必须补齐的规则答案/);
  assertMatch(markdown, /答案形式/);
  assertMatch(markdown, /当前未发现 P1 缺陷|## P0 缺陷/);
  assertMatch(markdown, /请给出驳回通知处理规则表/);
  assertMatch(markdown, /规则缺失/);
}

function run() {
  testBuildExportMarkdown();
  testBuildExportFileName();
  testBuildExportMarkdownV2();
  console.log("exportMarkdown checks passed");
}

run();
