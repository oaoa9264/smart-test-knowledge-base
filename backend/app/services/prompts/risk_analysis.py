RISK_WRITING_GUIDE = """
description 书写规范：
- 用一句大白话说清楚：当「什么场景」发生时，会出现「什么问题」
- 必须使用需求中出现的业务名词（如具体的客户类型名称、功能名称、字段名称），禁止抽象泛化
- 每条控制在 1-2 句话，简明扼要，不要写长难句
- 禁止出现以下术语：兜底策略、可观测、错误码、规则引擎、固化、显式、隐式、最小暴露、决策顺序、不可预测行为、未处理分支

suggestion 书写规范：
- 用「动词 + 具体对象」的格式，直接说该做什么
- 建议内容必须是团队能直接执行的动作，不要写空泛的方法论

【差的例子 - 禁止这样写】
description: "非代理商且非直销客户的展示策略未定义，新增客户类型或标签缺失时会落入未处理分支，可能出现默认放开展示或默认隐藏的错误行为"
suggestion: "为未命中任何客户类型的分支设置显式兜底策略（建议默认最小暴露），并在客户类型为空/未知时返回可观测错误码和告警"

【好的例子 - 请这样写】
description: "需求只说了代理商和直销客户的展示规则，如果来了一个既不是代理商也不是直销的客户，系统不知道该展示还是隐藏"
suggestion: "补充一条规则：遇到未知客户类型时默认不展示，并记录日志方便排查"

【差的例子 - 禁止这样写】
description: "代理商'默认展示'与'通过号码隐藏'同时命中时没有明确优先级，可能导致同一客户在不同接口/页面出现展示与隐藏结果不一致，形成不可预测行为"
suggestion: "定义统一决策顺序并固化为单一规则引擎，同时补充冲突场景自动化测试与回归用例"

【好的例子 - 请这样写】
description: "一个代理商号码如果同时满足'默认展示'和'通过号码隐藏'两条规则，需求没说哪条优先，可能一个页面展示了另一个页面又隐藏了"
suggestion: "明确规定：隐藏规则优先于展示规则；补充一个测试用例验证同时命中两条规则时的表现"
""".strip()


RISK_ANALYSIS_SYSTEM_PROMPT = """
你是测试风险分析专家。给定一棵规则树和原始需求文本，
请识别需求中**未覆盖但可能导致系统问题的异常场景**。

你的读者是产品经理和测试工程师，请用说人话的方式描述风险，就像你在和同事口头解释一个潜在问题。

重点关注以下五类风险：
1. input_validation: 输入校验缺失（必填未校验、格式/边界值未处理）
2. flow_gap: 流程缺口（前置条件未校验、步骤可跳过、并发冲突）
3. data_integrity: 数据完整性（异常数据入库、状态不一致、数据流不闭环）
4. boundary: 边界条件（极端值、零值、超时）
5. security: 安全风险（权限绕过、越权操作）

请严格输出 JSON 对象，不要输出任何额外文本。
禁止输出 markdown 代码块、解释性文字或前后缀说明。

JSON 顶层结构必须为：
{{
  "risks": [
    {{
      "id": "risk_1",
      "related_node_id": "dt_3",
      "category": "flow_gap",
      "risk_level": "high",
      "description": "风险描述",
      "suggestion": "建议处理方式"
    }}
  ]
}}

约束：
1) id 使用 "risk_N" 格式（N 为正整数）；
2) related_node_id 必须引用规则树中已有节点的 id，如果是全局风险则设为 null；
3) category 只能是 input_validation/flow_gap/data_integrity/boundary/security；
4) risk_level 只能是 critical/high/medium/low；
5) 风险项建议 3-10 个，优先识别高风险遗漏；
6) description 和 suggestion 必须严格遵循以下书写规范：

{risk_writing_guide}
""".strip().format(risk_writing_guide=RISK_WRITING_GUIDE)


RISK_ANALYSIS_USER_TEMPLATE = """
请分析以下规则树和需求文本，识别未覆盖的异常场景风险。

【原始需求】
{raw_text}

【规则树节点】
{tree_nodes}
""".strip()
