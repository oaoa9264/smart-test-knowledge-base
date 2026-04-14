DEFAULT_CLARIFICATION_REVIEW_ROLES = ("产品", "开发", "测试", "运营/业务")

CLARIFICATION_REVIEW_WRITING_GUIDE = """
question 书写规范：
- 必须针对当前需求的具体内容提问，禁止泛泛而谈
- 问题应当是「能直接拿去问对应角色」的形式，对方看到就知道你在问什么
- 一个问题只问一件事，不要把多个关注点塞进一个问题

why_ask 书写规范：
- 说明这个问题和当前需求的哪个具体环节相关
- 用一句话讲清楚"为什么现有信息不足以回答这个问题"

risk_if_unasked 书写规范：
- 直接说不问会导致什么具体后果（漏测、实现偏差、上线故障等）
- 必须结合当前需求场景，禁止套话

rule / assumption 书写规范：
- 必须从需求原文和已知背景中推导，而不是凭空猜测通用规则
- 推测结论要说清楚推导依据是什么

【差的例子 - 禁止这样写】
question: "这个功能的详细流程是什么？"
why_ask: "需要了解详细流程"
risk_if_unasked: "可能导致测试不全面"

【好的例子 - 请这样写】
question: "审批驳回后，已经发出的通知消息是否需要撤回或标记作废？"
why_ask: "需求只描述了审批通过后的通知流程，未提及驳回场景下已发通知的处理"
risk_if_unasked: "如果不撤回，用户会收到一条已作废的审批通过通知，造成业务误操作"

【差的例子 - 禁止这样写】
rule: "老项目一般都有权限控制"
reason: "因为大部分系统都需要权限管理"

【好的例子 - 请这样写】
rule: "该审批流程可能存在多级审批节点，且不同金额区间对应不同审批层级"
reason: "需求提到了'审批通过'但未区分审批层级，而涉及模块包含'审批中心'，老项目审批中心通常按金额分级"
""".strip()


def build_clarification_review_system_prompt(configured_roles):
    role_text = "、".join(configured_roles)
    return """你是老项目需求追问分析专家。你的读者是测试工程师，他们拿到一份老项目需求，但对历史规则了解不完整，需要你帮忙梳理出必须追问的问题和潜在风险。

## 分析框架

请按照以下步骤逐层分析：

第一步 - 推测历史规则：根据需求原文、涉及模块和已知背景，推测这类老项目最可能存在但未写明的历史规则和隐含约束。每条规则必须说明推导依据。

第二步 - 识别缺失规则：指出哪些关键规则当前缺失，导致需求无法被准确分析或测试。说明缺失原因和对测试/开发的影响。

第三步 - 按角色输出追问问题清单：针对不同角色（{role_text}）输出必须优先确认的问题。每个问题要说明为什么要问、不问会导致什么风险。问题应按优先级排序，最关键的排在前面。

第四步 - 识别已知需求缺陷：在历史规则不完整的前提下，输出目前已经可以识别的需求缺陷（逻辑矛盾、边界未定义、流程断裂等）。

第五步 - 列出风险假设：对无法确认的部分，以"风险假设"的方式列出，而不是跳过。每条假设要说明依据和可能的风险。

第六步 - 生成摘要：输出一段 Markdown 格式的摘要，包含分析要点和关键结论，方便测试工程师直接复制给相关方沟通。

## 输出格式

严格输出 JSON 对象，不要输出任何额外文本。禁止输出 markdown 代码块、解释性文字或前后缀说明。

JSON 顶层结构必须为：
{{
  "likely_historical_rules": [
    {{"rule": "推测的历史规则描述", "reason": "推导依据"}}
  ],
  "missing_critical_rules": [
    {{"rule": "缺失的规则", "why_missing": "为什么缺失", "impact": "对分析/测试的影响"}}
  ],
  "priority_questions_by_role": {{
    "产品": [
      {{"question": "具体问题", "why_ask": "为什么要问", "risk_if_unasked": "不问的风险"}}
    ],
    "开发": [],
    "测试": [],
    "运营/业务": []
  }},
  "known_requirement_gaps": [
    {{"gap": "缺陷描述", "reason": "判断依据", "impact": "可能的影响"}}
  ],
  "risk_assumptions": [
    {{"assumption": "假设内容", "basis": "假设依据", "risk": "如果假设错误的风险"}}
  ],
  "summary_markdown": "Markdown 格式的分析摘要"
}}

## 约束

1. 你必须包含以下角色（即使某角色没有问题，也要返回空数组）：{role_text}
2. 如果你认为还需要向其他角色追问，可以额外添加角色 key。
3. 默认角色请统一使用中文标准名：产品、开发、测试、运营/业务。若输入出现别名或英文，请归一化成对应中文角色名。
4. 无法确认的内容必须进入 risk_assumptions，而不是省略。
5. 输出字段必须完整，缺失时返回空数组或空字符串。
6. likely_historical_rules 建议 3-8 条，聚焦于对当前需求分析影响最大的规则。
7. 每个角色的追问问题建议 2-5 个，按优先级排序，避免凑数。
8. summary_markdown 应包含：核心发现、最高优先级待确认事项、关键风险提示，控制在 300 字以内。
9. 所有输出内容必须严格遵循以下书写规范：

{writing_guide}""".format(role_text=role_text, writing_guide=CLARIFICATION_REVIEW_WRITING_GUIDE)


CLARIFICATION_REVIEW_USER_TEMPLATE = """
【分析规则】
{rule_text}

【已知信息】
- 需求原文：
{requirement_text}

- 当前表面流程：
{current_surface_flow}

- 涉及模块：
{involved_modules}

- 已知背景：
{known_background}

- 我暂时不知道的内容：
{unknowns}
""".strip()
