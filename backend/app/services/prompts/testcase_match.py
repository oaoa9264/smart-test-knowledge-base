MATCH_SYSTEM_PROMPT = """
你是一个测试专家。你需要将测试用例匹配到规则树的节点上。
规则树描述了业务逻辑的条件、分支和动作。
对于每条测试用例，找出它验证了哪些规则节点。
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
""".strip()
