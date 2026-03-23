import React from "react";
import ReactDOMServer from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const markdown = [
  "# 闪信系统事实档案",
  "",
  "## 代码位置",
  "",
  "| 分类 | 入口 | 说明 |",
  "|---|---|---|",
  "| 模板与明细后台 | `FlashserviceController` | 模板列表、明细、审核、发送统计、数据报表、渠道统计 |",
].join("\n");

try {
  ReactDOMServer.renderToStaticMarkup(
    React.createElement(ReactMarkdown, { remarkPlugins: [remarkGfm] }, markdown),
  );
  console.log("PASS: GFM table markdown rendered successfully");
} catch (error) {
  console.error("FAIL: GFM table markdown crashed rendering");
  console.error(error instanceof Error ? error.stack : error);
  process.exit(1);
}
