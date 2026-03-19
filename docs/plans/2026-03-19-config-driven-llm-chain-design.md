# Config-Driven LLM Chain Design

## Goal

把当前硬编码的 `OpenAI -> 智谱` 回退链升级为“配置驱动的多 provider 链”，支持后续频繁调整模型、顺序和接入平台，同时统一项目内所有 LLM 相关能力在失败时的行为。

## Current Problems

1. `LLMClient` 目前在 [backend/app/services/llm_client.py](/Users/wanghu/Desktop/公司代码/smart-test-knowledge-base/backend/app/services/llm_client.py) 中写死了 provider 组链逻辑，扩展新模型需要改代码。
2. `OpenAIClient` 和 `ZhipuClient` 自己读环境变量，导致 provider 配置无法复用成“多实例”。
3. 各业务服务对 LLM 失败的处理不一致：
   - 有的回退本地规则逻辑
   - 有的回退 mock
   - 有的直接失败
4. 前端目前主要通过 `analysis_mode=mock_fallback` 理解失败语义，无法表达“所有模型都失败且没有本地兜底”的新状态。

## Design Decision

### 1. Provider 链改成配置驱动

新增统一配置：

```env
LLM_PROVIDER_CHAIN=main,backup,zhipu
```

每个 alias 对应一组 provider 配置：

```env
LLM_PROVIDER_MAIN_TYPE=openai_compatible
LLM_PROVIDER_MAIN_API_KEY=...
LLM_PROVIDER_MAIN_BASE_URL=...
LLM_PROVIDER_MAIN_TEXT_MODEL=gpt-5.4
LLM_PROVIDER_MAIN_VISION_MODEL=gpt-5.4
```

`LLMClient` 只负责：

1. 读取 `LLM_PROVIDER_CHAIN`
2. 逐个 alias 解析配置
3. 调用 provider factory 构建 client
4. 交给 `FallbackLLMClient` 处理顺序调用

### 2. 先按协议类型，不按品牌建模

短期支持：

- `openai_compatible`
- `zhipu`

后续如果真的需要原生 API，再增加：

- `anthropic`
- `gemini`

这样多数未来模型都可以直接复用 `openai_compatible`，避免每接一个新平台就新增一套业务适配。

### 2.1 `openai_compatible` 的实现决策

`openai_compatible` 这一类 provider 这次明确继续走现有的 OpenAI Python SDK streaming path，不改成基类的 `httpx` SSE 实现。

原因：

- 当前 [backend/app/services/openai_client.py](/Users/wanghu/Desktop/公司代码/smart-test-knowledge-base/backend/app/services/openai_client.py) 已有稳定测试覆盖
- 这次重构的核心目标是“配置驱动组链”和“统一失败语义”，不是替换 OpenAI 侧传输实现
- 先保留 SDK 路径，能把变量控制在 provider 组装层和服务失败语义层

后续如果确实需要把 `openai_compatible` 统一抽到 `httpx` SSE，再单独做一轮替换。

### 3. Provider alias 是一等公民

链路中的 `main`、`backup`、`zhipu` 不只是配置名字，也应作为运行时的 provider 标识：

- 日志打印 alias
- `get_last_provider()` 返回 alias
- API 返回 `llm_provider=main|backup|zhipu`

不要只返回通用类型名，否则多个 `openai_compatible` provider 无法区分命中哪一层。

### 4. 三层都失败时，不再走生产兜底

在正常 `llm` 模式下：

- provider 链中任一层成功：返回正常结果
- provider 链全部失败：返回空结果 + 统一失败元信息

不再自动回退到：

- 规则分句
- 关键词匹配
- mock provider
- 模板/静态 fallback

### 5. 仍然保留显式 mock 模式

如果环境变量明确指定：

- `ANALYZER_PROVIDER=mock`
- `AI_PARSE_PROVIDER=mock`

则仍允许走本地/mock 逻辑。

这意味着：

- `mock` 是人工开关
- 不是正常 `llm` 模式失败后的自动兜底

### 6. 兼容旧环境变量格式

迁移期保留旧格式兼容：

- 如果设置了 `LLM_PROVIDER_CHAIN`，使用新配置驱动链路
- 如果未设置 `LLM_PROVIDER_CHAIN`，回退到旧逻辑：
  - `OPENAI_API_KEY` 存在则装配旧 OpenAI provider
  - `ZHIPU_API_KEY` 存在则装配旧 Zhipu provider

兼容旧格式时需要打印 deprecation warning，提示部署尽快迁移到新配置，避免一次改动导致现有环境直接启动失败。

## Failure Contract

所有 LLM 结果统一补充：

```json
{
  "llm_status": "success|failed",
  "llm_provider": "main|backup|zhipu|null",
  "llm_message": "所有模型调用失败，未生成结果。请稍后重试或检查模型配置。"
}
```

兼容策略：

- 已有 `analysis_mode` 的接口先保留
- 失败时新增 `analysis_mode="llm_failed"`
- 前端逐步迁移到以 `llm_status` 为主

## Empty Result Rule

空结果由各服务自己定义，不在 API 层硬拼。

示例：

- `ai_parser`：`{nodes: [], risks: []}`
- `test_plan_generator`：`{test_plan: "", test_points: []}`
- `testcase_matcher`：`[]` 或空匹配列表
- `architecture_analyzer`：最小合法空壳结构

原因是每个服务的 schema 差异很大，统一在 API 层拼空对象会让语义和校验都变差。

## Exception Design

`FallbackLLMClient` 在链路耗尽时抛出：

- `AllLLMProvidersFailedError`

包含：

- `failed_providers`
- `last_error`
- `method_name`

这样业务层可以统一识别“provider 链全部失败”，而不是只拿到最后一个 provider 的错误。

## Provider-Specific Extras

provider 特有参数通过 alias 级 env 注入，不放到全局共享配置里。

当前需要明确支持的特例：

- Zhipu: `LLM_PROVIDER_<ALIAS>_THINKING_TYPE`

由 provider factory 解析后传给 `ZhipuClient`。这样不会把智谱特有参数泄漏到通用 client 接口中。

## Compatibility Strategy

分三步迁移：

1. 先完成配置驱动链和自定义异常，保持旧业务 fallback 不变
2. 再逐个服务去掉生产 fallback，改成空结果 + 失败元信息
3. 最后前端统一收敛到 `llm_status`

这能把风险拆开，避免一次性同时改 provider、服务语义和 UI。

## Non-Goals

这次不做：

1. 数据库存储 provider 配置
2. 管理台动态维护 provider 链
3. 不同 provider 的高级能力差异抽象
4. 全量移除所有历史 `analysis_mode` 字段

## Recommended Next Step

先按实施计划完成以下顺序：

1. provider client 参数化
2. provider registry + `LLM_PROVIDER_CHAIN`
3. `AllLLMProvidersFailedError`
4. 服务层统一失败语义
5. 前端和文档迁移
