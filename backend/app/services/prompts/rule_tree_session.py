from app.services.prompts.architecture import GENERATE_SYSTEM_PROMPT

GENERATE_USER_TEMPLATE = """
【任务】
请严格根据以下需求文本生成 decision_tree。

【核心原则】
- 只提取需求中明确描述的规则和条件，不要添加需求中未提及的任何假设
- 每个节点必须能在原始需求中找到对应描述
- 具体规则保持具体，不要泛化

【需求文本】
{requirement_text}
""".strip()

REVIEW_USER_PROMPT = """
你是测试设计审查专家。请审查你刚才生成的规则树，基于原始需求检查：
1) 是否遗漏了关键条件分支（尤其是异常/边界场景）
2) 是否有语义重复或冗余的节点
3) 节点粒度是否合理（既不过粗也不过细）
4) 父子关系是否逻辑正确
5) 是否引入了原始需求中未提及的概念、实体或条件（如需求未提"配置"就不应出现"根据配置"）
6) 是否将多条具体规则错误地泛化为一个抽象概念

【约束】
- 改进后的节点，保持原有 id 不变
- 新增节点使用新的 dt_N id
- 输出完整的 decision_tree JSON
- 如果无需改进，原样返回
- 如果发现幻觉/泛化节点，必须将其替换为忠实于原始需求的具体节点
""".strip()

INCREMENTAL_UPDATE_USER_TEMPLATE = """
需求已从版本 N 更新到版本 N+1，请基于已确认的规则树进行增量更新。

【旧版需求】
{old_requirement}

【新版需求】
{new_requirement}

【需求变更摘要】
{auto_diff}

【当前已确认的规则树】
{current_rule_tree_json}

【约束】
1) 未涉及变更的节点，必须保持 id、content、type、risk_level 等完全不变
2) 仅对涉及变更的部分进行 新增/修改/删除
3) 修改的节点保持原 id，更新 content 等字段
4) 新增节点使用新的 dt_N id（N 不与已有 id 冲突）
5) 需要删除的节点不要出现在输出中
6) 输出完整的 decision_tree JSON
""".strip()
