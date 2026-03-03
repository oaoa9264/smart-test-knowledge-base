export const RULE_TREE_THEME = "ruleTreeTheme";

let themeRegistered = false;

const ruleTreeThemeConfig = {
  backgroundColor: "#f7f9ff",
  lineColor: "#6f80c7",
  lineWidth: 2,
  lineStyle: "curve",
  lineRadius: 6,
  root: {
    shape: "rectangle",
    fillColor: "#323b52",
    color: "#ffffff",
    borderColor: "#323b52",
    borderWidth: 1,
    borderRadius: 12,
    fontSize: 16,
    fontWeight: "bold",
    paddingX: 20,
    paddingY: 12,
  },
  second: {
    shape: "rectangle",
    fillColor: "#eef2ff",
    color: "#2f3f8f",
    borderColor: "#8ea0ff",
    borderWidth: 1,
    borderRadius: 10,
    fontSize: 14,
    marginX: 88,
    marginY: 28,
    paddingX: 14,
    paddingY: 8,
  },
  node: {
    shape: "rectangle",
    fillColor: "#ffffff",
    color: "#334155",
    borderColor: "#c7d2fe",
    borderWidth: 1,
    borderRadius: 10,
    fontSize: 13,
    marginX: 56,
    marginY: 16,
    paddingX: 12,
    paddingY: 6,
  },
  generalization: {
    shape: "rectangle",
    fillColor: "#ffffff",
    color: "#334155",
    borderColor: "#c7d2fe",
    borderWidth: 1,
    borderRadius: 8,
    fontSize: 13,
  },
};

export function ensureRuleTreeTheme(MindMapCtor: {
  defineTheme: (name: string, config?: Record<string, unknown>) => Error | void;
}): void {
  if (themeRegistered) return;

  const maybeError = MindMapCtor.defineTheme(RULE_TREE_THEME, ruleTreeThemeConfig);
  if (maybeError instanceof Error && maybeError.message.includes("已存在")) {
    themeRegistered = true;
    return;
  }

  themeRegistered = true;
}
