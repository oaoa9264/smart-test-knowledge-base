const fs = require("fs");
const path = require("path");

const filePath = path.join(__dirname, "..", "src", "pages", "RuleTree", "RiskPanel.tsx");
const source = fs.readFileSync(filePath, "utf8");

const start = source.indexOf("const handleClarify = async () => {");
if (start === -1) {
  throw new Error("handleClarify not found");
}

const end = source.indexOf("const handleDelete = async", start);
if (end === -1) {
  throw new Error("handleClarify boundary not found");
}

const block = source.slice(start, end);

if (!block.includes("await loadRequirementInputs();")) {
  throw new Error("handleClarify should refresh requirement inputs after saving clarification");
}

console.log("check-clarify-refresh: ok");
