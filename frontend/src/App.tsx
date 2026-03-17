import { useEffect } from "react";
import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router-dom";
import { Layout, Menu, Select, Space, Typography, message } from "antd";
import {
  AppstoreOutlined,
  ClusterOutlined,
  FileTextOutlined,
  FireOutlined,
  FolderOpenOutlined,
  TableOutlined,
} from "@ant-design/icons";
import { fetchProjects, fetchRequirements } from "./api/projects";
import { useAppStore } from "./stores/appStore";
import ProjectListPage from "./pages/ProjectList";
import RuleTreePage from "./pages/RuleTree";
import TestCasesPage from "./pages/TestCases";
import CoveragePage from "./pages/Coverage";
import RecommendationPage from "./pages/Recommendation";
import ProductDocsPage from "./pages/ProductDocs";

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/", label: <Link to="/">项目与需求</Link>, icon: <FolderOpenOutlined /> },
  { key: "/rule-tree", label: <Link to="/rule-tree">规则树</Link>, icon: <ClusterOutlined /> },
  { key: "/test-cases", label: <Link to="/test-cases">用例管理</Link>, icon: <AppstoreOutlined /> },
  { key: "/coverage", label: <Link to="/coverage">覆盖矩阵</Link>, icon: <TableOutlined /> },
  { key: "/recommendation", label: <Link to="/recommendation">回归推荐</Link>, icon: <FireOutlined /> },
  { key: "/product-docs", label: <Link to="/product-docs">产品文档</Link>, icon: <FileTextOutlined /> },
];

function AppShell() {
  const location = useLocation();
  const {
    projects,
    requirements,
    selectedProjectId,
    selectedRequirementId,
    setProjects,
    setRequirements,
    setSelectedProjectId,
    setSelectedRequirementId,
  } = useAppStore();

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    try {
      const data = await fetchProjects();
      setProjects(data);
      if (!selectedProjectId && data.length > 0) {
        setSelectedProjectId(data[0].id);
      }
    } catch {
      message.error("加载项目失败");
    }
  };

  useEffect(() => {
    if (!selectedProjectId) {
      setRequirements([]);
      setSelectedRequirementId(null);
      return;
    }
    loadRequirements(selectedProjectId);
  }, [selectedProjectId]);

  const loadRequirements = async (projectId: number) => {
    try {
      const data = await fetchRequirements(projectId);
      setRequirements(data);
      if (data.length === 0) {
        setSelectedRequirementId(null);
      } else if (!data.find((item) => item.id === selectedRequirementId)) {
        setSelectedRequirementId(data[0].id);
      }
    } catch {
      message.error("加载需求失败");
    }
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light" width={220}>
        <div style={{ padding: 18, fontWeight: 700, color: "#0f3255" }}>智能测试结构平台</div>
        <Menu selectedKeys={[location.pathname]} mode="inline" items={menuItems} />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            borderBottom: "1px solid #e6edf5",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
            height: 72,
            paddingInline: 20,
          }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            需求 → 规则树 → 用例覆盖
          </Typography.Title>
          <Space wrap>
            <Select
              style={{ width: 220 }}
              placeholder="选择项目"
              value={selectedProjectId ?? undefined}
              onChange={(value) => {
                // 切换项目时先清空需求，避免短暂使用旧需求ID请求接口
                setSelectedRequirementId(null);
                setSelectedProjectId(value);
              }}
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
            />
            <Select
              style={{ width: 320 }}
              placeholder="选择需求"
              value={selectedRequirementId ?? undefined}
              onChange={(value) => setSelectedRequirementId(value)}
              options={(() => {
                const maxVersionByGroup = new Map<number, number>();
                for (const r of requirements) {
                  if (r.requirement_group_id != null) {
                    const cur = maxVersionByGroup.get(r.requirement_group_id) ?? 0;
                    if (r.version > cur) maxVersionByGroup.set(r.requirement_group_id, r.version);
                  }
                }
                return requirements.map((r) => {
                  const isLatest =
                    r.requirement_group_id != null &&
                    r.version === maxVersionByGroup.get(r.requirement_group_id);
                  const suffix = isLatest ? `v${r.version}(最新)` : `v${r.version}`;
                  return { label: `${r.title} ${suffix}`, value: r.id };
                });
              })()}
            />
          </Space>
        </Header>
        <Content style={{ margin: 16, padding: 20, background: "#fff", borderRadius: 12 }}>
          <Routes>
            <Route path="/" element={<ProjectListPage />} />
            <Route path="/rule-tree" element={<RuleTreePage />} />
            <Route path="/test-cases" element={<TestCasesPage />} />
            <Route path="/coverage" element={<CoveragePage />} />
            <Route path="/recommendation" element={<RecommendationPage />} />
            <Route path="/product-docs" element={<ProductDocsPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}
