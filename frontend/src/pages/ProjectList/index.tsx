import { useEffect, useState } from "react";
import {
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
import { useAppStore } from "../../stores/appStore";
import type { Project, Requirement } from "../../types";
import { getSourceTypeLabel } from "../../utils/enumLabels";

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
  const [projectForm] = Form.useForm();
  const [requirementForm] = Form.useForm();
  const [editProjectForm] = Form.useForm();
  const [editRequirementForm] = Form.useForm();

  useEffect(() => {
    reloadProjects();
  }, []);

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
                <List.Item.Meta title={item.name} description={item.description || "无描述"} />
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
        </Form>
      </Modal>

      <Modal
        title="需求详情"
        open={!!viewRequirement}
        footer={null}
        onCancel={() => setViewRequirement(null)}
        destroyOnClose
      >
        <Descriptions bordered column={1} size="small">
          <Descriptions.Item label="ID">{viewRequirement?.id}</Descriptions.Item>
          <Descriptions.Item label="标题">{viewRequirement?.title}</Descriptions.Item>
          <Descriptions.Item label="来源">{getSourceTypeLabel(viewRequirement?.source_type)}</Descriptions.Item>
          <Descriptions.Item label="需求原文">{viewRequirement?.raw_text}</Descriptions.Item>
        </Descriptions>
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
