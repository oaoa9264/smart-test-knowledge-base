# LLM 多模型接入与回退机制设计方案

## 一、背景与目标

当前项目：

- 已接入 **智谱 LLM（SSE）**
- 上层已存在：
  - 规则树解析 `/api/ai/parse`
  - 需求拆解 `/api/ai/architecture/analyze`
- 已具备：
  - LLM 失败 → Mock 兜底机制
  - JSON 结构校验与归一化逻辑
  - 超时/重试/参数配置能力

### 本次目标

实现：

> **OpenAI 优先 → 智谱 → 最终兜底（Mock）**

要求：

1. 不破坏现有接口
2. 不影响上层 Analyzer/Parser 逻辑
3. 保持 JSON 结构稳定
4. 支持未来继续扩展多模型

------

# 二、总体架构设计

## 2.1 分层结构

```
          ┌────────────────────────────┐
          │  Analyzer / Parser Layer   │
          │  (已有 Mock 兜底机制)       │
          └─────────────▲──────────────┘
                        │
                LLMClient 抽象层
                        │
        ┌───────────────┴───────────────┐
        │        FallbackLLMClient       │
        └───────────────▲───────────────┘
                        │
        ┌───────────────┴───────────────┐
        │  OpenAIClient  →  ZhipuClient  │
        └────────────────────────────────┘
```

执行顺序：

```
1️⃣ 先调用 OpenAI
2️⃣ OpenAI 失败 → 调用 智谱
3️⃣ 两者都失败 → 抛异常
4️⃣ 上层 Provider 捕获 → 走 MockAnalyzer / 规则兜底
```

------

# 三、改造范围

## 3.1 修改点汇总

| 模块                     | 修改类型 | 说明                         |
| ------------------------ | -------- | ---------------------------- |
| `.env.example`           | 新增配置 | OpenAI 相关变量              |
| `openai_client.py`       | 新增文件 | 实现 OpenAI 调用             |
| `fallback_llm_client.py` | 新增文件 | 实现顺序回退                 |
| `llm_client.py`          | 轻微修改 | 改为实例化 FallbackLLMClient |
| 单元测试                 | 扩展     | 新增优先级与回退测试         |

------

# 四、环境变量设计

新增：

```
OPENAI_API_KEY=
OPENAI_API_URL=https://api.openai.com/v1
OPENAI_TEXT_MODEL=
OPENAI_VISION_MODEL=
```

复用现有：

```
LLM_CONNECT_TIMEOUT
LLM_REQUEST_TIMEOUT
LLM_MAX_RETRIES
LLM_MAX_TOKENS
LLM_TEMPERATURE
```

不修改现有：

```
ZHIPU_API_KEY
ZHIPU_TEXT_MODEL
ZHIPU_VISION_MODEL
```

------

# 五、OpenAI 接入方案

## 5.1 采用 API

使用：

> **OpenAI Responses API（推荐）**

原因：

- 支持文本 + 多模态
- 支持 `json_schema` 强结构化输出
- 与当前两阶段模式匹配

------

## 5.2 JSON 输出策略（关键设计）

优先使用：

```
response_format = {
    "type": "json_schema",
    "json_schema": {...}
}
```

优势：

- 强约束
- 降低结构漂移
- 减少 Pydantic 校验失败

降级策略：

```
若模型不支持 json_schema
→ 自动降级 json_object
```

并强制 prompt 明确：

```
请严格输出 JSON，不要输出额外文本
```

------

## 5.3 Vision 支持

使用：

```
input_image
```

支持：

- URL
- base64 data URL

直接复用当前智谱图片转 base64 逻辑。

------

# 六、FallbackLLMClient 设计

## 6.1 核心逻辑

```python
class FallbackLLMClient:
    def __init__(self, primary, secondary):
        self.clients = [primary, secondary]

    def chat_with_json(...):
        for client in self.clients:
            try:
                return client.chat_with_json(...)
            except Exception:
                continue
        raise Exception("All LLM providers failed")
```

优先级：

```
[OpenAIClient, ZhipuClient]
```

------

## 6.2 为什么不在 LLMClient 内部做 Mock？

因为当前项目已经在：

- AnalyzerProvider 层
- Parser 层

做了 mock_fallback 机制。

保持职责单一：

```
LLMClient 只负责：
- 调模型
- 顺序回退
- 抛异常
```

------

# 七、异常与回退策略

| 场景          | 行为                |
| ------------- | ------------------- |
| OpenAI 超时   | 调用智谱            |
| OpenAI 400    | 调用智谱            |
| JSON 解析失败 | 调用智谱            |
| 两者都失败    | 抛异常              |
| 抛异常        | 上层走 MockAnalyzer |

------

# 八、测试方案

新增测试类型：

## 8.1 优先级测试

```
OpenAI 成功
→ 不应调用智谱
```

## 8.2 回退测试

```
OpenAI 抛错
→ 智谱成功
→ 返回智谱结果
```

## 8.3 双失败测试

```
OpenAI 抛错
智谱 抛错
→ 上层 mock_fallback 生效
```

------

# 九、日志增强建议

建议新增日志字段：

```
provider=openai
provider=zhipu
fallback_from=openai
```

用于：

- 定位频繁回退
- 识别 OpenAI 限流问题
- 判断是否全部落入 Mock

------

# 十、上线风险评估

| 风险          | 说明               | 对策             |
| ------------- | ------------------ | ---------------- |
| JSON 结构漂移 | 不同模型输出差异   | 使用 json_schema |
| 性能波动      | 不同模型延迟不同   | 保持超时参数一致 |
| 成本增加      | 双模型可能触发回退 | 监控回退比例     |
| 限流          | OpenAI 429         | 自动回退智谱     |

------

# 十一、未来扩展能力

该设计支持：

- 加入 Claude
- 加入本地 vLLM
- 加入 Azure OpenAI
- 动态权重调度
- A/B 测试模型质量

只需：

```
新增 Client
加入 FallbackLLMClient 顺序列表
```

------

# 十二、实施步骤

### 第一步：新增 OpenAIClient

实现：

- chat_with_json
- chat_with_vision

### 第二步：实现 FallbackLLMClient

顺序：

```
OpenAI → Zhipu
```

### 第三步：替换原 LLMClient 注入点

不改上层逻辑。

### 第四步：补单测

覆盖三种回退路径。

### 第五步：灰度发布

观察：

- fallback 次数
- mock_fallback 比例
- JSON 校验失败率

------

# 十三、方案总结

本方案特点：

- ✅ 不改接口
- ✅ 不改数据库
- ✅ 不破坏现有 Mock 兜底
- ✅ 支持未来扩展
- ✅ 最小侵入
- ✅ 易于回滚

------

如果你需要，我可以再给你一份：

- 📄 《技术评审版（含流程图 + 风险矩阵）》
- 📄 《实施清单 + 任务拆分（可直接进 Jira）》
- 📄 《代码结构目录改造图》

你想要哪种版本？