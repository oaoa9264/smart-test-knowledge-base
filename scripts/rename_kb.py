#!/usr/bin/env python3
"""Batch rename knowledge base files to Chinese and fix all internal links."""

import os
import re
import sys

KB_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge_base", "products",
)

# ── Old filename → New filename (basename only) ──────────────────────────
FILE_RENAME = {
    # 闪信
    "flashservice-fact-archive.md": "闪信-事实档案.md",
    "flashservice-send-report-main-chain.md": "闪信-发送与回执.md",
    "flashservice-template-authorization-chain.md": "闪信-模板与授权.md",
    "flashservice-stat-billing-chain.md": "闪信-统计与计费.md",
    # 短信
    "smsservice-fact-archive.md": "短信-事实档案.md",
    "smsservice-send-report-main-chain.md": "短信-发送与回执.md",
    "smsservice-template-channel-chain.md": "短信-模板与通道.md",
    "smsservice-stat-finance-integration-chain.md": "短信-统计与财务接入.md",
    # 质检
    "qualitytest-fact-archive.md": "质检-事实档案.md",
    "qualitytest-async-main-chain.md": "质检-异步处理.md",
    "qualitytest-callback-repair-fraud-sidecar.md": "质检-回调修复与反欺诈.md",
    "qualitytest-stat-report-consume-chain.md": "质检-统计报表与消耗.md",
    "qualitytest-rule-config-chain.md": "质检-规则配置.md",
    # 号码认证
    "telsign-telverify-fact-archive.md": "号码认证-事实档案.md",
    "telsign-package-upgrade-adjustment-chain.md": "号码认证-套餐升降级调账.md",
    "telsign-review-chain.md": "号码认证-审核.md",
    "telsign-跨链路公共概念说明.md": "号码认证-跨链路公共概念说明.md",
    "telsign-manual-price-billing-repair-chain.md": "号码认证-后台改价修账.md",
    "telsign-billing-contract-chain.md": "号码认证-计费与合同.md",
    "telsign-push-chain.md": "号码认证-推送.md",
    # 报表中心
    "report-center-fact-archive.md": "报表中心-事实档案.md",
    "report-api-interface-chain.md": "报表中心-对外接口.md",
    "report-weekly-push-chain.md": "报表中心-周报与推送.md",
    "report-ops-stat-chain.md": "报表中心-运营统计.md",
    # 推送对比
    "push-data-check-fact-archive.md": "推送对比-事实档案.md",
    "push-data-check-chain.md": "推送对比-数据校验.md",
    # 标记监测
    "sign-phonesign-fact-archive.md": "标记监测-事实档案.md",
    "signv2-import-query-main-chain.md": "标记监测-导入与查询.md",
    "signmodel-prediction-chain.md": "标记监测-模型预测.md",
    # 财务管理
    "finance-fact-archive.md": "财务管理-事实档案.md",
    "finance-manual-repair-chain.md": "财务管理-修账.md",
    "finance-product-billing.md": "财务管理-产品计费.md",
    "finance-invoice-chain.md": "财务管理-开票.md",
    # 商户与权限
    "merchant-account-permission-fact-archive.md": "商户与权限-事实档案.md",
    "merchant-product-opening-quota-inheritance-chain.md": "商户与权限-产品开通与额度继承.md",
    "merchant-basic-info-sales-ownership-chain.md": "商户与权限-基本信息与销售归属.md",
    "admin-user-role-menu-permission-chain.md": "商户与权限-用户角色与菜单权限.md",
    # 神盾码号卫士
    "shendun-code-guardian-fact-archive.md": "神盾码号卫士-事实档案.md",
    "shendun-跨链路公共概念说明.md": "神盾码号卫士-跨链路公共概念说明.md",
    "shendun-report-chain.md": "神盾码号卫士-报表与运营分析.md",
    "shendun-import-chain.md": "神盾码号卫士-导入.md",
    "shendun-risksms-chain.md": "神盾码号卫士-短信风险.md",
    "shendun-config-rule-chain.md": "神盾码号卫士-配置与规则.md",
    "shendun-stat-consume-chain.md": "神盾码号卫士-统计与消耗.md",
}


def _replace_link_target(match: re.Match) -> str:
    """Replace old filename in a markdown link target, keep link text."""
    full = match.group(0)
    text = match.group(1)
    path = match.group(2)

    basename = os.path.basename(path)
    if basename in FILE_RENAME:
        new_basename = FILE_RENAME[basename]
        new_path = path.replace(basename, new_basename)
        # If link text is the old filename itself, update it too
        new_text = FILE_RENAME.get(text, text)
        return f"[{new_text}]({new_path})"
    return full


def _remove_local_links(match: re.Match) -> str:
    """Convert markdown links with absolute local paths to inline code."""
    text = match.group(1)
    return f"`{text}`"


def fix_content(content: str) -> str:
    """Fix all links in a markdown file's content."""
    # 1. Convert absolute local-path links to inline code
    #    Pattern: [text](/Users/wanghu/...)
    content = re.sub(
        r'\[([^\]]+)\]\(/Users/[^\)]+\)',
        _remove_local_links,
        content,
    )

    # 2. Update markdown link targets that reference renamed files
    #    Pattern: [text](path/to/old-name.md) or [text](old-name.md)
    content = re.sub(
        r'\[([^\]]+)\]\(([^\)]*\.md)\)',
        _replace_link_target,
        content,
    )

    return content


def main():
    dry_run = "--dry-run" in sys.argv

    # ── Phase 1: Fix content in all .md files ────────────────────────────
    md_files = []
    for root, dirs, files in os.walk(KB_ROOT):
        for f in files:
            if f.endswith(".md"):
                md_files.append(os.path.join(root, f))

    print(f"Found {len(md_files)} markdown files")

    content_changes = 0
    for fpath in md_files:
        with open(fpath, "r", encoding="utf-8") as fh:
            original = fh.read()

        updated = fix_content(original)

        if updated != original:
            content_changes += 1
            if dry_run:
                print(f"  [WOULD FIX] {os.path.relpath(fpath, KB_ROOT)}")
            else:
                with open(fpath, "w", encoding="utf-8") as fh:
                    fh.write(updated)
                print(f"  [FIXED] {os.path.relpath(fpath, KB_ROOT)}")

    print(f"Content fixes: {content_changes} files")

    # ── Phase 2: Rename files ────────────────────────────────────────────
    rename_count = 0
    for root, dirs, files in os.walk(KB_ROOT):
        for f in files:
            if f in FILE_RENAME:
                old_path = os.path.join(root, f)
                new_path = os.path.join(root, FILE_RENAME[f])
                if old_path == new_path:
                    continue
                rename_count += 1
                if dry_run:
                    print(f"  [WOULD RENAME] {f} -> {FILE_RENAME[f]}")
                else:
                    os.rename(old_path, new_path)
                    print(f"  [RENAMED] {f} -> {FILE_RENAME[f]}")

    print(f"Renames: {rename_count} files")
    if dry_run:
        print("\n(dry run — no changes made)")


if __name__ == "__main__":
    main()
