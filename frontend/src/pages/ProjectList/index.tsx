import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  createProject,
  createRequirement,
  deleteProject,
  deleteRequirement,
  fetchProjects,
  fetchRequirements,
  updateProject,
  updateRequirement,
} from "../../api/projects";
import { getErrorMessage } from "../../api/client";
import {
  fetchLatestNormalizedRequirementDocTask,
  startNormalizedRequirementDocTask,
} from "../../api/normalizedRequirementDocTasks";
import { fetchProductDocs } from "../../api/productDocs";
import { useAppStore } from "../../stores/appStore";
import type {
  NormalizedRequirementDocPreview,
  NormalizedRequirementDocTask,
  ProductDoc,
  Project,
  Requirement,
} from "../../types";
import { getSourceTypeLabel } from "../../utils/enumLabels";
import ReactMarkdown from "react-markdown";

function buildPreviewFromTask(
  requirement: Requirement,
  task: NormalizedRequirementDocTask,
): NormalizedRequirementDocPreview {
  return {
    title: requirement.title,
    markdown: task.result_markdown || "",
    basis_hash: task.basis_hash || "",
    uses_fresh_snapshot: task.uses_fresh_snapshot,
    snapshot_stale: task.snapshot_stale,
    llm_status: "success",
    llm_provider: task.llm_provider,
    llm_message: null,
  };
}

export default function ProjectListPage() {
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

  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [requirementModalOpen, setRequirementModalOpen] = useState(false);
  const [viewProject, setViewProject] = useState<Project | null>(null);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [viewRequirement, setViewRequirement] = useState<Requirement | null>(null);
  const [editingRequirement, setEditingRequirement] = useState<Requirement | null>(null);
  const [productDocs, setProductDocs] = useState<ProductDoc[]>([]);
  const [normalizedDocOpen, setNormalizedDocOpen] = useState(false);
  const [normalizedDocLoading, setNormalizedDocLoading] = useState(false);
  const [normalizedDocDownloading, setNormalizedDocDownloading] = useState(false);
  const [normalizedDocPreview, setNormalizedDocPreview] = useState<NormalizedRequirementDocPreview | null>(null);
  const [normalizedDocTask, setNormalizedDocTask] = useState<NormalizedRequirementDocTask | null>(null);
  const normalizedDocPollTimerRef = useRef<number | null>(null);
  const previousNormalizedDocTaskStatusRef = useRef<string | null>(null);
  const [projectForm] = Form.useForm();
  const [requirementForm] = Form.useForm();
  const [editProjectForm] = Form.useForm();
  const [editRequirementForm] = Form.useForm();

  useEffect(() => {
    reloadProjects();
    loadProductDocs();
  }, []);

  const loadProductDocs = async () => {
    try {
      const docs = await fetchProductDocs();
      setProductDocs(docs);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    if (selectedProjectId) {
      reloadRequirements(selectedProjectId);
    }
  }, [selectedProjectId]);

  const reloadProjects = async (activeProjectId?: number | null) => {
    try {
      const data = await fetchProjects();
      setProjects(data);
      const currentProjectId = activeProjectId === undefined ? selectedProjectId : activeProjectId;
      if (data.length === 0) {
        setSelectedProjectId(null);
        return;
      }
      if (!currentProjectId || !data.find((item) => item.id === currentProjectId)) {
        setSelectedProjectId(data[0].id);
      }
    } catch {
      message.error("加载项目失败");
    }
  };

  const reloadRequirements = async (projectId: number, activeRequirementId?: number | null) => {
    try {
      const data = await fetchRequirements(projectId);
      setRequirements(data);
      const currentRequirementId =
        activeRequirementId === undefined ? selectedRequirementId : activeRequirementId;
      if (data.length === 0) {
        setSelectedRequirementId(null);
        return;
      }
      if (!currentRequirementId || !data.find((item) => item.id === currentRequirementId)) {
        setSelectedRequirementId(data[0].id);
      }
    } catch {
      message.error("加载需求失败");
    }
  };

  const handleCreateProject = async () => {
    const values = await projectForm.validateFields();
    const project = await createProject(values);
    setProjectModalOpen(false);
    projectForm.resetFields();
    message.success("项目已创建");
    await reloadProjects(project.id);
    setSelectedProjectId(project.id);
  };

  const handleCreateRequirement = async () => {
    if (!selectedProjectId) {
      message.warning("请先选择项目");
      return;
    }
    const values = await requirementForm.validateFields();
    const req = await createRequirement(selectedProjectId, { ...values, source_type: "prd" });
    setRequirementModalOpen(false);
    requirementForm.resetFields();
    message.success("需求已创建");
    await reloadRequirements(selectedProjectId, req.id);
    setSelectedRequirementId(req.id);
  };

  const handleEditProject = (project: Project) => {
    setEditingProject(project);
    editProjectForm.setFieldsValue({
      name: project.name,
      description: project.description,
      product_code: project.product_code || undefined,
    });
  };

  const handleUpdateProject = async () => {
    if (!editingProject) return;
    const values = await editProjectForm.validateFields();
    await updateProject(editingProject.id, values);
    message.success("项目已更新");
    setEditingProject(null);
    editProjectForm.resetFields();
    await reloadProjects(editingProject.id);
  };

  const handleDeleteProject = async (projectId: number) => {
    await deleteProject(projectId);
    message.success("项目已删除");
    if (selectedProjectId === projectId) {
      setSelectedProjectId(null);
      setRequirements([]);
    }
    await reloadProjects(null);
  };

  const handleEditRequirement = (requirement: Requirement) => {
    setEditingRequirement(requirement);
    editRequirementForm.setFieldsValue({
      title: requirement.title,
      raw_text: requirement.raw_text,
      source_type: requirement.source_type,
    });
  };

  const handleUpdateRequirement = async () => {
    if (!selectedProjectId || !editingRequirement) return;
    const values = await editRequirementForm.validateFields();
    await updateRequirement(selectedProjectId, editingRequirement.id, values);
    message.success("需求已更新");
    setEditingRequirement(null);
    editRequirementForm.resetFields();
    await reloadRequirements(selectedProjectId, editingRequirement.id);
  };

  const handleDeleteRequirement = async (requirementId: number) => {
    if (!selectedProjectId) return;
    await deleteRequirement(selectedProjectId, requirementId);
    message.success("需求已删除");
    await reloadRequirements(selectedProjectId, selectedRequirementId === requirementId ? null : selectedRequirementId);
  };

  const openNormalizedDocPreview = async (requirement: Requirement) => {
    if (
      normalizedDocTask?.requirement_id === requirement.id &&
      normalizedDocTask.status === "completed" &&
      normalizedDocTask.result_markdown
    ) {
      setNormalizedDocPreview(buildPreviewFromTask(requirement, normalizedDocTask));
      setNormalizedDocOpen(true);
      return;
    }

    setNormalizedDocPreview(null);
    setNormalizedDocLoading(true);
    try {
      const accepted = await startNormalizedRequirementDocTask(requirement.id);
      setNormalizedDocTask(accepted.task);
      message.success("已开始后台生成规范化需求文档");
    } catch (error) {
      setNormalizedDocOpen(false);
      setNormalizedDocPreview(null);
      message.error(getErrorMessage(error, "发起规范化需求文档生成失败"));
    } finally {
      setNormalizedDocLoading(false);
    }
  };

  const refreshNormalizedDocTask = async (requirementId: number) => {
    const task = await fetchLatestNormalizedRequirementDocTask(requirementId);
    setNormalizedDocTask(task);
    return task;
  };

  const hydrateNormalizedDocTask = async (requirement: Requirement) => {
    try {
      const task = await fetchLatestNormalizedRequirementDocTask(requirement.id);
      previousNormalizedDocTaskStatusRef.current = task?.status || null;
      setNormalizedDocTask(task);
    } catch (error) {
      message.error(getErrorMessage(error, "加载规范化需求文档任务失败"));
    }
  };

  const handleDownloadNormalizedDoc = async () => {
    if (!viewRequirement || !normalizedDocPreview) return;
    setNormalizedDocDownloading(true);
    try {
      const blob = new Blob([normalizedDocPreview.markdown], { type: "text/markdown;charset=utf-8" });
      const filename = `requirement-${viewRequirement.id}.md`;
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      message.success("Markdown 下载成功");
    } catch (error) {
      message.error(getErrorMessage(error, "下载 Markdown 失败"));
    } finally {
      setNormalizedDocDownloading(false);
    }
  };

  useEffect(() => {
    if (normalizedDocPollTimerRef.current) {
      window.clearTimeout(normalizedDocPollTimerRef.current);
      normalizedDocPollTimerRef.current = null;
    }
    if (!viewRequirement || !normalizedDocTask) return;
    if (normalizedDocTask.status !== "queued" && normalizedDocTask.status !== "running") return;

    normalizedDocPollTimerRef.current = window.setTimeout(() => {
      void refreshNormalizedDocTask(viewRequirement.id).catch((error) => {
        message.error(getErrorMessage(error, "刷新规范化需求文档任务失败"));
      });
    }, 2000);

    return () => {
      if (normalizedDocPollTimerRef.current) {
        window.clearTimeout(normalizedDocPollTimerRef.current);
        normalizedDocPollTimerRef.current = null;
      }
    };
  }, [normalizedDocTask, viewRequirement]);

  useEffect(() => {
    const nextStatus = normalizedDocTask?.status || null;
    const prevStatus = previousNormalizedDocTaskStatusRef.current;
    previousNormalizedDocTaskStatusRef.current = nextStatus;

    if (!nextStatus || prevStatus === null || prevStatus === nextStatus) return;

    if (nextStatus === "completed" && normalizedDocTask?.result_markdown && viewRequirement) {
      setNormalizedDocPreview(buildPreviewFromTask(viewRequirement, normalizedDocTask));
      setNormalizedDocOpen(true);
      message.success("规范化需求文档生成完成");
      return;
    }

    if (nextStatus === "failed") {
      setNormalizedDocOpen(false);
      setNormalizedDocPreview(null);
      message.error(normalizedDocTask?.last_error || "模型调用失败，未生成规范化需求文档");
    }
  }, [normalizedDocTask, viewRequirement]);

  useEffect(() => {
    setNormalizedDocTask(null);
    previousNormalizedDocTaskStatusRef.current = null;
    if (!viewRequirement) {
      setNormalizedDocPreview(null);
      setNormalizedDocOpen(false);
      return;
    }
    void hydrateNormalizedDocTask(viewRequirement);
  }, [viewRequirement?.id]);

  const requirementColumns = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "标题", dataIndex: "title" },
    {
      title: "版本",
      dataIndex: "version",
      width: 80,
      render: (v: number) => <Tag color="blue">v{v}</Tag>,
    },
    { title: "来源", dataIndex: "source_type", width: 120, render: (v: string) => getSourceTypeLabel(v) },
    {
      title: "操作",
      width: 220,
      render: (_: unknown, row: Requirement) => (
        <Space size="small">
          <Button
            type="link"
            onClick={(e) => {
              e.stopPropagation();
              setViewRequirement(row);
            }}
          >
            查看
          </Button>
          <Button
            type="link"
            onClick={(e) => {
              e.stopPropagation();
              handleEditRequirement(row);
            }}
          >
            修改
          </Button>
          <Popconfirm
            title="确认删除该需求吗？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => handleDeleteRequirement(row.id)}
          >
            <Button type="link" danger onClick={(e) => e.stopPropagation()}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Row gutter={16}>
      <Col span={9}>
        <Card
          title="项目列表"
          extra={
            <Button type="primary" onClick={() => setProjectModalOpen(true)}>
              新建项目
            </Button>
          }
        >
          <List
            dataSource={projects}
            rowKey="id"
            renderItem={(item: Project) => (
              <List.Item
                onClick={() => setSelectedProjectId(item.id)}
                style={{
                  cursor: "pointer",
                  background: item.id === selectedProjectId ? "#f0f7ff" : "transparent",
                  borderRadius: 8,
                  paddingInline: 8,
                }}
                extra={
                  <Space onClick={(e) => e.stopPropagation()}>
                    <Button type="link" onClick={() => setViewProject(item)}>
                      查看
                    </Button>
                    <Button type="link" onClick={() => handleEditProject(item)}>
                      修改
                    </Button>
                    <Popconfirm
                      title="确认删除该项目吗？"
                      okText="删除"
                      cancelText="取消"
                      onConfirm={() => handleDeleteProject(item.id)}
                    >
                      <Button type="link" danger>
                        删除
                      </Button>
                    </Popconfirm>
                  </Space>
                }
              >
                <List.Item.Meta
                  title={
                    <Space>
                      {item.name}
                      {item.product_code && <Tag color="cyan" style={{ fontSize: 11 }}>{item.product_code}</Tag>}
                    </Space>
                  }
                  description={item.description || "无描述"}
                />
              </List.Item>
            )}
          />
        </Card>
      </Col>
      <Col span={15}>
        <Card
          title="需求列表"
          extra={
            <Space>
              <Typography.Text type="secondary">当前项目: {selectedProjectId ?? "未选择"}</Typography.Text>
              <Button type="primary" onClick={() => setRequirementModalOpen(true)}>
                新建需求
              </Button>
            </Space>
          }
        >
          <Table<Requirement>
            size="small"
            columns={requirementColumns}
            dataSource={requirements}
            rowKey="id"
            pagination={false}
            onRow={(row) => ({
              onClick: () => setSelectedRequirementId(row.id),
            })}
          />
        </Card>
      </Col>

      <Modal title="新建项目" open={projectModalOpen} onCancel={() => setProjectModalOpen(false)} onOk={handleCreateProject}>
        <Form layout="vertical" form={projectForm}>
          <Form.Item label="项目名称" name="name" rules={[{ required: true, message: "请输入项目名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="项目描述" name="description">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="所属产品" name="product_code">
            <Select
              allowClear
              placeholder="选择关联的产品文档"
              options={productDocs.map((d) => ({ label: `${d.name} (${d.product_code})`, value: d.product_code }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新建需求"
        open={requirementModalOpen}
        onCancel={() => setRequirementModalOpen(false)}
        onOk={handleCreateRequirement}
      >
        <Form layout="vertical" form={requirementForm}>
          <Form.Item label="需求标题" name="title" rules={[{ required: true, message: "请输入需求标题" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="需求原文" name="raw_text" rules={[{ required: true, message: "请输入需求文本" }]}>
            <Input.TextArea rows={6} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="项目详情"
        open={!!viewProject}
        footer={null}
        onCancel={() => setViewProject(null)}
        destroyOnClose
      >
        <Descriptions bordered column={1} size="small">
          <Descriptions.Item label="ID">{viewProject?.id}</Descriptions.Item>
          <Descriptions.Item label="项目名称">{viewProject?.name}</Descriptions.Item>
          <Descriptions.Item label="项目描述">{viewProject?.description || "-"}</Descriptions.Item>
          <Descriptions.Item label="所属产品">{viewProject?.product_code || "-"}</Descriptions.Item>
        </Descriptions>
      </Modal>

      <Modal
        title="修改项目"
        open={!!editingProject}
        onCancel={() => {
          setEditingProject(null);
          editProjectForm.resetFields();
        }}
        onOk={handleUpdateProject}
      >
        <Form layout="vertical" form={editProjectForm}>
          <Form.Item label="项目名称" name="name" rules={[{ required: true, message: "请输入项目名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="项目描述" name="description">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="所属产品" name="product_code">
            <Select
              allowClear
              placeholder="选择关联的产品文档"
              options={productDocs.map((d) => ({ label: `${d.name} (${d.product_code})`, value: d.product_code }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="需求详情"
        open={!!viewRequirement}
        footer={[
          <Button
            key="export"
            type="primary"
            loading={normalizedDocLoading || normalizedDocTask?.status === "queued" || normalizedDocTask?.status === "running"}
            onClick={() => viewRequirement && void openNormalizedDocPreview(viewRequirement)}
          >
            导出规范化需求
          </Button>,
        ]}
        onCancel={() => {
          setViewRequirement(null);
          setNormalizedDocOpen(false);
          setNormalizedDocPreview(null);
          setNormalizedDocTask(null);
        }}
        destroyOnClose
      >
        <Descriptions bordered column={1} size="small">
          <Descriptions.Item label="ID">{viewRequirement?.id}</Descriptions.Item>
          <Descriptions.Item label="标题">{viewRequirement?.title}</Descriptions.Item>
          <Descriptions.Item label="来源">{getSourceTypeLabel(viewRequirement?.source_type)}</Descriptions.Item>
          <Descriptions.Item label="需求原文">{viewRequirement?.raw_text}</Descriptions.Item>
        </Descriptions>
        {normalizedDocTask?.status === "queued" || normalizedDocTask?.status === "running" ? (
          <Alert
            style={{ marginTop: 16 }}
            type="info"
            showIcon
            message="规范化需求文档仍在后台生成中，重新打开后已自动恢复任务状态。"
          />
        ) : null}
        {normalizedDocTask?.status === "completed" ? (
          <Alert
            style={{ marginTop: 16 }}
            type="success"
            showIcon
            message="上次规范化需求文档已生成完成，可直接点击“导出规范化需求”查看预览。"
          />
        ) : null}
        {normalizedDocTask?.status === "failed" ? (
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message={normalizedDocTask.last_error || "上次规范化需求文档生成失败，可重新发起生成。"}
          />
        ) : null}
      </Modal>

      <Modal
        title="规范化需求预览"
        open={normalizedDocOpen}
        width={900}
        footer={[
          <Button key="download" type="primary" loading={normalizedDocDownloading} onClick={() => void handleDownloadNormalizedDoc()}>
            下载 Markdown
          </Button>,
        ]}
        onCancel={() => {
          setNormalizedDocOpen(false);
          setNormalizedDocPreview(null);
        }}
        destroyOnClose
      >
        {normalizedDocLoading ? (
          <Typography.Text type="secondary">加载中...</Typography.Text>
        ) : normalizedDocPreview ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Alert
              type={normalizedDocPreview.uses_fresh_snapshot ? "success" : normalizedDocPreview.snapshot_stale ? "warning" : "info"}
              showIcon
              message={
                normalizedDocPreview.uses_fresh_snapshot
                  ? "已复用最新快照"
                  : normalizedDocPreview.snapshot_stale
                    ? "当前快照已过期，本次文档基于实时输入整理"
                    : "暂无快照参考，本次文档基于实时输入整理"
              }
            />
            <div
              style={{
                maxHeight: 560,
                overflow: "auto",
                padding: 16,
                border: "1px solid #f0f0f0",
                borderRadius: 8,
                background: "#fafafa",
              }}
            >
              <ReactMarkdown>{normalizedDocPreview.markdown}</ReactMarkdown>
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        title="修改需求"
        open={!!editingRequirement}
        onCancel={() => {
          setEditingRequirement(null);
          editRequirementForm.resetFields();
        }}
        onOk={handleUpdateRequirement}
      >
        <Form layout="vertical" form={editRequirementForm}>
          <Form.Item label="需求标题" name="title" rules={[{ required: true, message: "请输入需求标题" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="来源" name="source_type" rules={[{ required: true, message: "请选择来源" }]}>
            <Select
              options={[
                { label: "需求文档", value: "prd" },
                { label: "流程图", value: "flowchart" },
                { label: "接口文档", value: "api_doc" },
              ]}
            />
          </Form.Item>
          <Form.Item label="需求原文" name="raw_text" rules={[{ required: true, message: "请输入需求文本" }]}>
            <Input.TextArea rows={6} />
          </Form.Item>
        </Form>
      </Modal>
    </Row>
  );
}
