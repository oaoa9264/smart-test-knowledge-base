import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Row,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  FileTextOutlined,
  PlusOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import type { ProductDoc, ProductDocDetail, ProductDocUpdate } from "../../types";
import {
  applyDocUpdate,
  deleteProductDoc,
  fetchDocUpdates,
  fetchProductDoc,
  fetchProductDocs,
  importProductDoc,
  rejectDocUpdate,
  suggestDocUpdate,
  updateChunk,
} from "../../api/productDocs";

const updateStatusLabels: Record<string, { text: string; color: string }> = {
  pending: { text: "待审核", color: "warning" },
  approved: { text: "已通过", color: "success" },
  rejected: { text: "已拒绝", color: "error" },
};

export default function ProductDocsPage() {
  const [docs, setDocs] = useState<ProductDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<ProductDocDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importForm] = Form.useForm();
  const [updates, setUpdates] = useState<ProductDocUpdate[]>([]);
  const [updatesLoading, setUpdatesLoading] = useState(false);
  const [editChunkModal, setEditChunkModal] = useState<{ chunkId: number; content: string } | null>(null);
  const [editChunkForm] = Form.useForm();
  const [manualBackfillOpen, setManualBackfillOpen] = useState(false);
  const [manualBackfillForm] = Form.useForm();

  useEffect(() => {
    loadDocs();
  }, []);

  const loadDocs = async () => {
    setLoading(true);
    try {
      const data = await fetchProductDocs();
      setDocs(data);
    } catch {
      message.error("加载产品文档列表失败");
    } finally {
      setLoading(false);
    }
  };

  const loadDocDetail = async (productCode: string) => {
    setDetailLoading(true);
    try {
      const detail = await fetchProductDoc(productCode);
      setSelectedDoc(detail);
      loadUpdates(detail.id);
    } catch {
      message.error("加载文档详情失败");
    } finally {
      setDetailLoading(false);
    }
  };

  const loadUpdates = async (docId: number) => {
    setUpdatesLoading(true);
    try {
      const data = await fetchDocUpdates(docId);
      setUpdates(data);
    } catch {
      // ignore
    } finally {
      setUpdatesLoading(false);
    }
  };

  const handleImport = async () => {
    const values = await importForm.validateFields();
    try {
      await importProductDoc(values);
      message.success("产品文档导入成功");
      setImportModalOpen(false);
      importForm.resetFields();
      await loadDocs();
    } catch {
      message.error("导入失败");
    }
  };

  const handleDelete = async (productCode: string) => {
    try {
      await deleteProductDoc(productCode);
      message.success("已删除");
      if (selectedDoc?.product_code === productCode) {
        setSelectedDoc(null);
        setUpdates([]);
      }
      await loadDocs();
    } catch {
      message.error("删除失败");
    }
  };

  const handleApplyUpdate = async (updateId: number) => {
    try {
      await applyDocUpdate(updateId);
      message.success("更新已应用");
      if (selectedDoc) {
        loadDocDetail(selectedDoc.product_code);
      }
    } catch {
      message.error("应用失败");
    }
  };

  const handleRejectUpdate = async (updateId: number) => {
    try {
      await rejectDocUpdate(updateId);
      message.success("已拒绝");
      if (selectedDoc) {
        loadUpdates(selectedDoc.id);
      }
    } catch {
      message.error("拒绝失败");
    }
  };

  const handleEditChunk = async () => {
    if (!editChunkModal || !selectedDoc) return;
    const values = await editChunkForm.validateFields();
    try {
      await updateChunk(selectedDoc.product_code, editChunkModal.chunkId, values.content);
      message.success("段落已更新");
      setEditChunkModal(null);
      loadDocDetail(selectedDoc.product_code);
    } catch {
      message.error("更新失败");
    }
  };

  const handleManualBackfill = async () => {
    if (!selectedDoc) {
      message.warning("请先选择产品文档");
      return;
    }
    const values = await manualBackfillForm.validateFields();
    try {
      await suggestDocUpdate({
        product_doc_id: selectedDoc.id,
        clarification_text: values.clarification_text,
        supplement_text: values.supplement_text,
      });
      message.success("知识补录建议已生成");
      setManualBackfillOpen(false);
      manualBackfillForm.resetFields();
      loadUpdates(selectedDoc.id);
    } catch {
      message.error("知识补录失败");
    }
  };

  const updateColumns = [
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (s: string) => {
        const info = updateStatusLabels[s] || { text: s, color: "default" };
        return <Tag color={info.color}>{info.text}</Tag>;
      },
    },
    {
      title: "段落 ID",
      dataIndex: "chunk_id",
      width: 80,
      render: (v: number | null) => v ?? "-",
    },
    {
      title: "风险项 ID",
      dataIndex: "risk_item_id",
      width: 120,
      render: (v: string | null) => v ? <Typography.Text copyable style={{ fontSize: 11 }}>{v.slice(0, 8)}...</Typography.Text> : "-",
    },
    {
      title: "操作",
      width: 160,
      render: (_: unknown, row: ProductDocUpdate) => {
        if (row.status !== "pending") return <Typography.Text type="secondary">-</Typography.Text>;
        return (
          <Space size="small">
            <Button
              size="small"
              type="link"
              onClick={() => {
                Modal.info({
                  title: "更新建议对比",
                  width: 700,
                  content: (
                    <div>
                      <Typography.Title level={5}>原始内容</Typography.Title>
                      <Typography.Paragraph style={{ background: "#fff1f0", padding: 12, borderRadius: 6, whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}>
                        {row.original_content || "(空)"}
                      </Typography.Paragraph>
                      <Typography.Title level={5}>建议内容</Typography.Title>
                      <Typography.Paragraph style={{ background: "#f6ffed", padding: 12, borderRadius: 6, whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}>
                        {row.suggested_content || "(空)"}
                      </Typography.Paragraph>
                    </div>
                  ),
                });
              }}
            >
              查看
            </Button>
            <Popconfirm title="确认应用此更新？" onConfirm={() => handleApplyUpdate(row.id)} okText="应用" cancelText="取消">
              <Button size="small" type="primary" icon={<CheckCircleOutlined />}>
                应用
              </Button>
            </Popconfirm>
            <Popconfirm title="确认拒绝此更新？" onConfirm={() => handleRejectUpdate(row.id)} okText="拒绝" cancelText="取消">
              <Button size="small" danger icon={<CloseCircleOutlined />}>
                拒绝
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <Row gutter={16}>
      <Col span={8}>
        <Card
          title="产品文档列表"
          extra={
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setImportModalOpen(true)}>
              导入文档
            </Button>
          }
        >
          {loading ? (
            <Spin />
          ) : docs.length === 0 ? (
            <Empty description="暂无产品文档" />
          ) : (
            <List
              dataSource={docs}
              rowKey="id"
              renderItem={(item) => (
                <List.Item
                  onClick={() => loadDocDetail(item.product_code)}
                  style={{
                    cursor: "pointer",
                    background: selectedDoc?.product_code === item.product_code ? "#f0f7ff" : "transparent",
                    borderRadius: 8,
                    paddingInline: 8,
                  }}
                  extra={
                    <Space onClick={(e) => e.stopPropagation()}>
                      <Popconfirm title="确认删除该产品文档吗？" onConfirm={() => handleDelete(item.product_code)} okText="删除" cancelText="取消">
                        <Button type="link" danger>删除</Button>
                      </Popconfirm>
                    </Space>
                  }
                >
                  <List.Item.Meta
                    avatar={<FileTextOutlined style={{ fontSize: 20, color: "#1890ff" }} />}
                    title={
                      <Space>
                        {item.name}
                        <Tag color="blue">v{item.version}</Tag>
                      </Space>
                    }
                    description={item.product_code}
                  />
                </List.Item>
              )}
            />
          )}
        </Card>
      </Col>
      <Col span={16}>
        {detailLoading ? (
          <Card><Spin /></Card>
        ) : selectedDoc ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Card
              title={`${selectedDoc.name} (v${selectedDoc.version})`}
              size="small"
              extra={
                <Button onClick={() => setManualBackfillOpen(true)}>
                  手工补录知识
                </Button>
              }
            >
              <Descriptions size="small" column={2}>
                <Descriptions.Item label="产品标识">{selectedDoc.product_code}</Descriptions.Item>
                <Descriptions.Item label="版本">{selectedDoc.version}</Descriptions.Item>
                <Descriptions.Item label="描述" span={2}>{selectedDoc.description || "-"}</Descriptions.Item>
                <Descriptions.Item label="段落数">{selectedDoc.chunks.length}</Descriptions.Item>
              </Descriptions>
            </Card>

            <Card title="文档段落" size="small">
              {selectedDoc.chunks.length === 0 ? (
                <Empty description="暂无段落" />
              ) : (
                <Collapse
                  ghost
                  defaultActiveKey={[]}
                  items={selectedDoc.chunks.map((chunk) => ({
                    key: String(chunk.id),
                    label: (
                      <Space>
                        <Tag>{chunk.stage_key}</Tag>
                        <span>{chunk.title}</span>
                      </Space>
                    ),
                    extra: (
                      <Button
                        size="small"
                        type="link"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditChunkModal({ chunkId: chunk.id, content: chunk.content });
                          editChunkForm.setFieldsValue({ content: chunk.content });
                        }}
                      >
                        编辑
                      </Button>
                    ),
                    children: (
                      <Typography.Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 13, maxHeight: 300, overflow: "auto" }}>
                        {chunk.content}
                      </Typography.Paragraph>
                    ),
                  }))}
                />
              )}
            </Card>

            <Card title="文档更新记录" size="small">
              <Table<ProductDocUpdate>
                size="small"
                loading={updatesLoading}
                columns={updateColumns}
                dataSource={updates}
                rowKey="id"
                pagination={false}
                locale={{ emptyText: "暂无更新记录" }}
              />
            </Card>
          </div>
        ) : (
          <Card>
            <Empty description="请从左侧选择一个产品文档" />
          </Card>
        )}
      </Col>

      <Modal
        title="导入产品文档"
        open={importModalOpen}
        onCancel={() => setImportModalOpen(false)}
        onOk={handleImport}
        width={700}
        okText="导入"
      >
        <Form layout="vertical" form={importForm}>
          <Form.Item label="产品标识" name="product_code" rules={[{ required: true, message: "请输入产品标识" }]}>
            <Input placeholder="如 telriskv2" />
          </Form.Item>
          <Form.Item label="产品名称" name="name" rules={[{ required: true, message: "请输入产品名称" }]}>
            <Input placeholder="如 神盾码号卫士" />
          </Form.Item>
          <Form.Item label="产品描述" name="description">
            <Input placeholder="产品简介（可选）" />
          </Form.Item>
          <Form.Item label="文档内容（Markdown）" name="content" rules={[{ required: true, message: "请粘贴 Markdown 文档内容" }]}>
            <Input.TextArea rows={12} placeholder="粘贴 Markdown 格式的产品文档，系统将按 ## 标题自动分块" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑段落"
        open={!!editChunkModal}
        onCancel={() => setEditChunkModal(null)}
        onOk={handleEditChunk}
        width={700}
        okText="保存"
      >
        <Form layout="vertical" form={editChunkForm}>
          <Form.Item label="段落内容" name="content" rules={[{ required: true, message: "请输入内容" }]}>
            <Input.TextArea rows={12} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="手工补录知识"
        open={manualBackfillOpen}
        onCancel={() => setManualBackfillOpen(false)}
        onOk={handleManualBackfill}
        width={700}
        okText="生成建议"
      >
        <Form layout="vertical" form={manualBackfillForm}>
          <Form.Item
            label="补充知识"
            name="supplement_text"
            rules={[{ required: true, message: "请输入补充知识内容" }]}
          >
            <Input.TextArea rows={6} placeholder="请输入需要补录到产品文档中的自由文本知识" />
          </Form.Item>
          <Form.Item
            label="补录说明"
            name="clarification_text"
            rules={[{ required: true, message: "请输入补录说明" }]}
          >
            <Input.TextArea rows={4} placeholder="说明为什么需要补录这段知识" />
          </Form.Item>
        </Form>
      </Modal>
    </Row>
  );
}
