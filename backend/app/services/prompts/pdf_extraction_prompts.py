STRICT_EXTRACTION_SYSTEM_PROMPT = """你是需求文档事实提取助手。

任务：
1. 只提取 PDF 中能够直接支持的事实，不要脑补。
2. 将内容归纳到以下字段：requirement_text、current_surface_flow、involved_modules、known_background、unknowns。
3. 每个字段都要给出 evidence，简要说明来自哪一页或哪段文字。
4. 如果字段没有足够依据，value 和 evidence 返回空字符串。
5. conflicts 仅用于记录文档内部明显冲突，无法确认时返回空数组。

严格输出 JSON 对象，不要输出额外说明。"""


STRICT_EXTRACTION_USER_TEMPLATE = """
请基于以下 PDF 提取信息输出结构化结果。

【全文提取】
{full_text}

【视觉理解笔记】
{vision_notes}

【附加标记】
- text_extraction_failed: {text_extraction_failed}

输出结构：
{{
  "fields": {{
    "requirement_text": {{"value": "", "evidence": ""}},
    "current_surface_flow": {{"value": "", "evidence": ""}},
    "involved_modules": {{"value": "", "evidence": ""}},
    "known_background": {{"value": "", "evidence": ""}},
    "unknowns": {{"value": "", "evidence": ""}}
  }},
  "conflicts": [
    {{"field": "", "description": "", "evidence": ""}}
  ]
}}
""".strip()


INFER_EXTRACTION_SYSTEM_PROMPT = """你是需求补充推断助手。

基于已有严格提取结果、全文和视觉笔记，补充更完整的测试视角总结。
要求：
1. 可以做保守推断，但必须在 evidence 中说明这是基于哪部分信息归纳。
2. 仍然只输出固定 5 个字段。
3. conflicts 始终返回空数组。

严格输出 JSON 对象。"""


INFER_EXTRACTION_USER_TEMPLATE = """
请基于以下信息生成补充推断结果。

【严格提取结果】
{strict_result}

【全文提取】
{full_text}

【视觉理解笔记】
{vision_notes}

输出结构：
{{
  "fields": {{
    "requirement_text": {{"value": "", "evidence": ""}},
    "current_surface_flow": {{"value": "", "evidence": ""}},
    "involved_modules": {{"value": "", "evidence": ""}},
    "known_background": {{"value": "", "evidence": ""}},
    "unknowns": {{"value": "", "evidence": ""}}
  }},
  "conflicts": []
}}
""".strip()


VISION_NOTES_SYSTEM_PROMPT = """你是 PDF 页面视觉理解助手。

请阅读多页需求文档截图，输出对测试工程师有帮助的事实笔记：
1. 识别流程、模块、表格、阈值、特殊说明。
2. 用简洁中文分点列出。
3. 仅总结图片中能直接看到的内容，不要补充猜测。"""
