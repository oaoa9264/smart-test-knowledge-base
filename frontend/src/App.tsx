import { useEffect, useMemo, useState } from "react";
import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router-dom";
import { Button, ConfigProvider, Empty, Layout, Menu, Result, Select, Space, Typography, message } from "antd";
import zhCN from "antd/locale/zh_CN";
import dayjs from "dayjs";
import "dayjs/locale/zh-cn";
import {
  AppstoreOutlined,
  ClusterOutlined,
  FileTextOutlined,
  FireOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
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
import ClarificationReviewPage from "./pages/ClarificationReview";
import { trackEvent } from "./utils/telemetry";

dayjs.locale("zh-cn");

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/", label: <Link to="/">项目与需求</Link>, icon: <FolderOpenOutlined /> },
  { key: "/rule-tree", label: <Link to="/rule-tree">规则树</Link>, icon: <ClusterOutlined /> },
  { key: "/test-cases", label: <Link to="/test-cases">用例管理</Link>, icon: <AppstoreOutlined /> },
  { key: "/coverage", label: <Link to="/coverage">覆盖矩阵</Link>, icon: <TableOutlined /> },
  { key: "/recommendation", label: <Link to="/recommendation">回归推荐</Link>, icon: <FireOutlined /> },
  { key: "/product-docs", label: <Link to="/product-docs">产品知识库</Link>, icon: <FileTextOutlined /> },
  { key: "/clarification-review", label: <Link to="/clarification-review">追问分析</Link>, icon: <QuestionCircleOutlined /> },
];

const PAGE_TITLE_MAP: Record<string, string> = {
  "/": "项目与需求",
  "/rule-tree": "规则树",
  "/test-cases": "用例管理",
  "/coverage": "覆盖矩阵",
  "/recommendation": "回归推荐",
  "/product-docs": "产品知识库",
  "/clarification-review": "追问分析",
};

function resolvePageTitle(pathname: string): string {
  if (PAGE_TITLE_MAP[pathname]) return PAGE_TITLE_MAP[pathname];
  const firstSegment = "/" + pathname.split("/")[1];
  return PAGE_TITLE_MAP[firstSegment] ?? "智能测试结构平台";
}

function NotFoundPage() {
  return (
    <Result
      status="404"
      title="页面走丢了"
      subTitle="抱歉，你访问的页面不存在或已被删除。"
      extra={
        <Link to="/">
          <Button type="primary">返回首页</Button>
        </Link>
      }
    />
  );
}

function AppShell() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    const raw = window.localStorage.getItem("smart-test-sider-collapsed");
    if (raw === "1") return true;
    if (raw === "0") return false;
    try {
      return window.matchMedia?.("(max-width: 992px)")?.matches ?? false;
    } catch {
      return false;
    }
  });
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

  useEffect(() => {
    const title = resolvePageTitle(location.pathname);
    if (typeof document !== "undefined") {
      document.title = `${title} · 智能测试结构平台`;
    }
    trackEvent("page.view", { path: location.pathname, title });
  }, [location.pathname]);

  const pageTitle = resolvePageTitle(location.pathname);

  const selectedMenuKey = useMemo(() => {
    const match = menuItems.find((item) => location.pathname === item.key || location.pathname.startsWith(`${item.key}/`));
    return match ? match.key : "/";
  }, [location.pathname]);

  const requirementOptions = useMemo(() => {
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
      const versionSuffix = isLatest ? `v${r.version} (最新)` : `v${r.version}`;
      return {
        label: r.title,
        value: r.id,
        title: r.title,
        versionSuffix,
        searchText: `${r.title} v${r.version}`.toLowerCase(),
      };
    });
  }, [requirements]);

  const handleSiderCollapse = (next: boolean) => {
    setCollapsed(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("smart-test-sider-collapsed", next ? "1" : "0");
    }
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        theme="light"
        width={220}
        collapsible
        collapsed={collapsed}
        onCollapse={handleSiderCollapse}
        breakpoint="lg"
      >
        <div
          style={{
            padding: collapsed ? "18px 12px" : 18,
            fontWeight: 700,
            color: "#0f3255",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {collapsed ? "STK" : "智能测试结构平台"}
        </div>
        <Menu selectedKeys={[selectedMenuKey]} mode="inline" items={menuItems} />
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
            {pageTitle}
          </Typography.Title>
          <Space wrap>
            <Select
              style={{ width: 220 }}
              placeholder="选择项目"
              value={selectedProjectId ?? undefined}
              onChange={(value) => {
                setSelectedRequirementId(null);
                setSelectedProjectId(value);
              }}
              showSearch
              optionFilterProp="label"
              notFoundContent={<Empty description="暂无项目" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
            />
            <Select
              style={{ width: 360 }}
              placeholder="选择需求"
              value={selectedRequirementId ?? undefined}
              onChange={(value) => setSelectedRequirementId(value)}
              showSearch
              optionFilterProp="label"
              listHeight={360}
              filterOption={(input, option) => {
                const raw =
                  (option as { searchText?: string; label?: string } | undefined)?.searchText ??
                  (option?.label as string | undefined) ??
                  "";
                return raw.toLowerCase().includes(input.toLowerCase());
              }}
              optionRender={(option) => {
                const data = option.data as
                  | { title?: string; versionSuffix?: string; label?: string }
                  | undefined;
                return (
                  <div style={{ lineHeight: 1.25, padding: "2px 0" }}>
                    <div
                      style={{
                        fontWeight: 500,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={data?.title || (data?.label as string | undefined)}
                    >
                      {data?.title || (data?.label as string | undefined)}
                    </div>
                    <div style={{ fontSize: 11, color: "#8a99a8" }}>
                      {data?.versionSuffix}
                    </div>
                  </div>
                );
              }}
              notFoundContent={
                selectedProjectId ? (
                  <Empty description="当前项目下暂无需求" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <Empty description="请先选择项目" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )
              }
              options={requirementOptions}
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
            <Route path="/clarification-review" element={<ClarificationReviewPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </ConfigProvider>
  );
}
