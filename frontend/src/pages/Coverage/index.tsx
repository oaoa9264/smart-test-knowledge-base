import { useEffect, useMemo, useState } from "react";
import { Alert, Card, Col, Progress, Row, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { fetchCoverage } from "../../api/coverage";
import { useAppStore } from "../../stores/appStore";
import type { CoverageMatrix, CoverageRow, NodeType } from "../../types";
import { getNodeTypeLabel, getRiskLevelLabel } from "../../utils/enumLabels";

const riskWeight: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };

const nodeTypeColor: Record<NodeType, string> = {
  root: "default",
  condition: "blue",
  branch: "purple",
  action: "green",
  exception: "orange",
};

const nodeTypeFilters = [
  { text: "动作", value: "action" },
  { text: "分支", value: "branch" },
  { text: "异常", value: "exception" },
  { text: "条件", value: "condition" },
  { text: "根节点", value: "root" },
];

export default function CoveragePage() {
  const { selectedProjectId, selectedRequirementId } = useAppStore();
  const [data, setData] = useState<CoverageMatrix | null>(null);

  useEffect(() => {
    if (!selectedProjectId || !selectedRequirementId) {
      setData(null);
      return;
    }
    fetchCoverage(selectedProjectId, selectedRequirementId)
      .then(setData)
      .catch(() => message.error("加载覆盖矩阵失败"));
  }, [selectedProjectId, selectedRequirementId]);

  const coverageRate = useMemo(() => {
    if (!data) return 0;
    return Math.round((data.summary.coverage_rate || 0) * 100);
  }, [data]);

  const allNodeCount = useMemo(() => {
    if (!data) return 0;
    return (data.summary.total_nodes || 0) + (data.summary.structural_nodes || 0);
  }, [data]);

  if (!selectedProjectId) {
    return <Alert type="info" message="请先选择项目" />;
  }
  if (!selectedRequirementId) {
    return <Alert type="info" message="请先选择需求，再查看该需求的节点覆盖率" />;
  }

  const columns: ColumnsType<CoverageRow> = [
    {
      title: "规则节点",
      dataIndex: "content",
      render: (text: string, row: CoverageRow) => (
        <span style={row.coverable ? undefined : { color: "#999" }}>{text}</span>
      ),
    },
    {
      title: "节点类型",
      dataIndex: "node_type",
      width: 100,
      filters: nodeTypeFilters,
      onFilter: (value, record) => record.node_type === value,
      render: (type: NodeType, row: CoverageRow) => (
        <Tag color={nodeTypeColor[type] || "default"}>
          {getNodeTypeLabel(type)}
          {!row.coverable && " (结构)"}
        </Tag>
      ),
    },
    {
      title: "风险等级",
      dataIndex: "risk_level",
      width: 100,
      sorter: (a, b) => riskWeight[a.risk_level] - riskWeight[b.risk_level],
      defaultSortOrder: "descend",
      render: (risk: string) => {
        const color =
          risk === "critical" ? "red" : risk === "high" ? "volcano" : risk === "medium" ? "orange" : "green";
        return <Tag color={color}>{getRiskLevelLabel(risk)}</Tag>;
      },
    },
    {
      title: "覆盖用例数",
      dataIndex: "covered_cases",
      width: 110,
      render: (num: number, row: CoverageRow) => {
        if (!row.coverable) return <span style={{ color: "#bbb" }}>-</span>;
        const color = num === 0 ? "#cf1322" : num === 1 ? "#d48806" : "#237804";
        return <span style={{ color, fontWeight: 700 }}>{num}</span>;
      },
    },
    {
      title: "未覆盖路径数",
      dataIndex: "uncovered_paths",
      width: 120,
      render: (num: number, row: CoverageRow) => {
        if (!row.coverable) return <span style={{ color: "#bbb" }}>-</span>;
        return num > 0 ? <Tag color="error">{num}</Tag> : "-";
      },
    },
  ];

  return (
    <div>
      <Row gutter={16}>
        <Col span={8}>
          <Card title="节点覆盖率">
            <Progress type="circle" percent={coverageRate} />
            <Typography.Paragraph style={{ marginTop: 12 }}>
              已覆盖 {data?.summary.covered_nodes || 0} / {data?.summary.total_nodes || 0} 个可测试节点
            </Typography.Paragraph>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              共 {allNodeCount} 个节点，其中 {data?.summary.total_nodes || 0} 个可测试，
              {data?.summary.structural_nodes || 0} 个结构性节点不计入覆盖率
            </Typography.Text>
          </Card>
        </Col>
        <Col span={16}>
          <Card title="高风险未覆盖告警">
            {(data?.summary.uncovered_critical || []).length > 0 ? (
              <Alert
                type="error"
                message={`存在 ${(data?.summary.uncovered_critical || []).length} 个严重风险可测试节点未覆盖`}
                description={(data?.summary.uncovered_critical || []).join(", ")}
              />
            ) : (
              <Alert type="success" message="当前严重风险可测试节点均已覆盖" />
            )}
          </Card>
        </Col>
      </Row>

      <Card title="覆盖矩阵" style={{ marginTop: 16 }}>
        <Table<CoverageRow>
          rowKey="node_id"
          size="small"
          pagination={{ pageSize: 10 }}
          dataSource={data?.rows || []}
          columns={columns}
          rowClassName={(record) => (record.coverable ? "" : "coverage-structural-row")}
        />
      </Card>

      <style>{`
        .coverage-structural-row {
          background: #fafafa;
        }
        .coverage-structural-row:hover > td {
          background: #f5f5f5 !important;
        }
      `}</style>
    </div>
  );
}
