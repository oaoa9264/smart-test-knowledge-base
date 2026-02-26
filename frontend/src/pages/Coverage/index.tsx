import { useEffect, useMemo, useState } from "react";
import { Alert, Card, Col, Progress, Row, Table, Tag, Typography, message } from "antd";
import { fetchCoverage } from "../../api/coverage";
import { useAppStore } from "../../stores/appStore";
import type { CoverageMatrix, CoverageRow } from "../../types";
import { getRiskLevelLabel } from "../../utils/enumLabels";

const riskWeight: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };

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

  if (!selectedProjectId) {
    return <Alert type="info" message="请先选择项目" />;
  }
  if (!selectedRequirementId) {
    return <Alert type="info" message="请先选择需求，再查看该需求的节点覆盖率" />;
  }

  return (
    <div>
      <Row gutter={16}>
        <Col span={8}>
          <Card title="节点覆盖率">
            <Progress type="circle" percent={coverageRate} />
            <Typography.Paragraph style={{ marginTop: 12 }}>
              已覆盖 {data?.summary.covered_nodes || 0} / {data?.summary.total_nodes || 0} 个规则节点
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col span={16}>
          <Card title="高风险未覆盖告警">
            {(data?.summary.uncovered_critical || []).length > 0 ? (
              <Alert
                type="error"
                message={`存在 ${(data?.summary.uncovered_critical || []).length} 个严重风险节点未覆盖`}
                description={(data?.summary.uncovered_critical || []).join(", ")}
              />
            ) : (
              <Alert type="success" message="当前严重风险节点均已覆盖" />
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
          columns={[
            { title: "规则节点", dataIndex: "content" },
            {
              title: "风险等级",
              dataIndex: "risk_level",
              sorter: (a, b) => riskWeight[a.risk_level] - riskWeight[b.risk_level],
              defaultSortOrder: "descend",
              render: (risk) => {
                const color =
                  risk === "critical" ? "red" : risk === "high" ? "volcano" : risk === "medium" ? "orange" : "green";
                return <Tag color={color}>{getRiskLevelLabel(risk)}</Tag>;
              },
            },
            {
              title: "覆盖用例数",
              dataIndex: "covered_cases",
              render: (num) => {
                const color = num === 0 ? "#cf1322" : num === 1 ? "#d48806" : "#237804";
                return <span style={{ color, fontWeight: 700 }}>{num}</span>;
              },
            },
            {
              title: "未覆盖路径数",
              dataIndex: "uncovered_paths",
              render: (num) => (num > 0 ? <Tag color="error">{num}</Tag> : "-"),
            },
          ]}
        />
      </Card>
    </div>
  );
}
