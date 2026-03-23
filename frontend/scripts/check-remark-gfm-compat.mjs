import React from "react";
import ReactDOMServer from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const markdown = [
  "# GFM Table",
  "",
  "| 分类 | 入口 | 说明 |",
  "|---|---|---|",
  "| 模板与明细后台 | `FlashserviceController` | 模板列表、明细、审核、发送统计、数据报表、渠道统计 |",
].join("\n");

try {
  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement(ReactMarkdown, { remarkPlugins: [remarkGfm] }, markdown),
  );
  if (!html.includes("<table>")) {
    throw new Error(`expected table markup, got: ${html}`);
  }
  console.log("PASS: remark-gfm rendered table markup");
} catch (error) {
  console.error("FAIL: remark-gfm could not render table markdown");
  console.error(error instanceof Error ? error.stack : error);
  process.exit(1);
}
