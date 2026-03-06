MATCH_SYSTEM_PROMPT = """
你是一个测试专家。你需要将测试用例匹配到规则树的节点上。
规则树描述了业务逻辑的条件、分支和动作。每个节点有 node_type 属性：
- root：需求标题/根节点，仅用于组织结构，不可测试
- condition：描述判断条件，本身不直接可测试
- action：具体行为/操作，可直接测试
- branch：分支结果，可直接测试
- exception：异常/边界场景，可直接测试

对于每条测试用例，找出它验证了哪些规则节点。
优先匹配 action、branch、exception 类型的节点，避免匹配到 root 节点。
只有当用例明确验证某个条件判断本身时，才匹配 condition 节点。
请仅返回 JSON。
""".strip()


MATCH_USER_TEMPLATE = """
## 规则树节点
{nodes_json}

## 待匹配测试用例
{cases_json}

请返回 JSON 对象：
{{
  "matches": [
    {{
      "case_index": 0,
      "matched_node_ids": ["node_id_1", "node_id_2"],
      "confidence": "high",
      "reason": "该用例验证了..."
    }}
  ]
}}

约束：
1) confidence 仅允许 high/medium/low/none
2) matched_node_ids 只能从给定节点 ID 中选择
3) 未命中时返回空数组并设置 confidence=none
4) 优先匹配 node_type 为 action/branch/exception 的可测试节点
5) 不要将用例匹配到 root 类型节点
""".strip()
