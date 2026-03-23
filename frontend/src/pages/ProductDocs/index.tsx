import { useEffect, useMemo, useState } from "react";
import {
  Card,
  Col,
  Empty,
  Row,
  Space,
  Spin,
  Tag,
  Tree,
  Typography,
} from "antd";
import {
  BookOutlined,
  FileTextOutlined,
  FolderOutlined,
  LinkOutlined,
} from "@ant-design/icons";
import type { DataNode } from "antd/es/tree";
import type { ProductDoc, ProductDocChunk, ProductDocDetail } from "../../types";
import { fetchProductDoc, fetchProductDocs } from "../../api/productDocs";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const CHAIN_TYPE_META: Record<string, { color: string; label: string }> = {
  overview: { color: "blue", label: "总档" },
  chain: { color: "green", label: "链路" },
  "common-concepts": { color: "orange", label: "公共概念" },
};

function inferChainType(chainKey: string | null | undefined): string {
  if (!chainKey || chainKey === "overview") return "overview";
  if (chainKey === "common-concepts") return "common-concepts";
  return "chain";
}

function groupChunksByChain(chunks: ProductDocChunk[]): Map<string, ProductDocChunk[]> {
  const map = new Map<string, ProductDocChunk[]>();
  for (const chunk of chunks) {
    const key = chunk.chain_key || "overview";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(chunk);
  }
  return map;
}

function deriveDisplayName(chainKey: string): string {
  if (chainKey === "overview") return "系统事实档案";
  if (chainKey === "common-concepts") return "跨链路公共概念";
  // Strip domain prefix: everything before the first hyphen
  // e.g. "闪信-发送与回执" → "发送与回执"
  const idx = chainKey.indexOf("-");
  if (idx > 0) return chainKey.slice(idx + 1);
  return chainKey;
}

export default function ProductDocsPage() {
  const [docs, setDocs] = useState<ProductDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<ProductDocDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedChainKey, setSelectedChainKey] = useState<string | null>(null);

  useEffect(() => {
    loadDocs();
  }, []);

  const loadDocs = async () => {
    setLoading(true);
    try {
      const data = await fetchProductDocs();
      setDocs(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const loadDocDetail = async (productCode: string) => {
    setDetailLoading(true);
    setSelectedChainKey(null);
    try {
      const detail = await fetchProductDoc(productCode);
      setSelectedDoc(detail);
    } catch {
      // ignore
    } finally {
      setDetailLoading(false);
    }
  };

  // Build tree data from docs + chunks
  const treeData: DataNode[] = useMemo(() => {
    return docs.map((doc) => ({
      key: `doc:${doc.product_code}`,
      title: (
        <Space size={4}>
          <span>{doc.name}</span>
        </Space>
      ),
      icon: <FolderOutlined />,
      children: [], // populated after doc is loaded
    }));
  }, [docs]);

  // Build chain tree for selected doc
  const chainTreeData: DataNode[] = useMemo(() => {
    if (!selectedDoc) return [];
    const chainMap = groupChunksByChain(selectedDoc.chunks);
    const nodes: DataNode[] = [];

    // Sort: overview first, then chains, then common-concepts
    const sortedKeys = [...chainMap.keys()].sort((a, b) => {
      const typeOrder = { overview: 0, chain: 1, "common-concepts": 2 };
      const ta = typeOrder[inferChainType(a) as keyof typeof typeOrder] ?? 1;
      const tb = typeOrder[inferChainType(b) as keyof typeof typeOrder] ?? 1;
      return ta - tb || a.localeCompare(b);
    });

    for (const chainKey of sortedKeys) {
      const chunks = chainMap.get(chainKey) || [];
      const chainType = inferChainType(chainKey);
      const meta = CHAIN_TYPE_META[chainType] || CHAIN_TYPE_META.chain;
      nodes.push({
        key: `chain:${chainKey}`,
        title: (
          <Space size={4}>
            <span>{deriveDisplayName(chainKey)}</span>
            <Tag color={meta.color} style={{ fontSize: 10, lineHeight: "16px", padding: "0 4px" }}>
              {meta.label}
            </Tag>
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              {chunks.length}段
            </Typography.Text>
          </Space>
        ),
        icon: chainType === "overview" ? <BookOutlined /> : <FileTextOutlined />,
      });
    }
    return nodes;
  }, [selectedDoc]);

  // Get content for selected chain
  const selectedChainContent = useMemo(() => {
    if (!selectedDoc || !selectedChainKey) return null;
    const chainMap = groupChunksByChain(selectedDoc.chunks);
    const chunks = chainMap.get(selectedChainKey);
    if (!chunks || chunks.length === 0) return null;
    return chunks.map((c) => c.content).join("\n\n");
  }, [selectedDoc, selectedChainKey]);

  const selectedChainChunks = useMemo(() => {
    if (!selectedDoc || !selectedChainKey) return [];
    const chainMap = groupChunksByChain(selectedDoc.chunks);
    return chainMap.get(selectedChainKey) || [];
  }, [selectedDoc, selectedChainKey]);

  // Map filename → chain_key for in-app link resolution
  const filenameToChainKey = useMemo(() => {
    if (!selectedDoc) return new Map<string, string>();
    const map = new Map<string, string>();
    for (const chunk of selectedDoc.chunks) {
      if (chunk.source_file) {
        const basename = chunk.source_file.split("/").pop() || "";
        if (basename && !map.has(basename)) {
          map.set(basename, chunk.chain_key || "overview");
        }
      }
    }
    return map;
  }, [selectedDoc]);

  const markdownComponents = useMemo(
    () => ({
      a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children?: React.ReactNode }) => {
        if (href && href.endsWith(".md")) {
          const basename = href.split("/").pop() || "";
          const targetKey = filenameToChainKey.get(basename);
          if (targetKey) {
            return (
              <a
                {...props}
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  setSelectedChainKey(targetKey);
                }}
                style={{ color: "#1890ff", cursor: "pointer" }}
              >
                {children}
              </a>
            );
          }
          // Cross-domain or unresolvable — render as plain text
          return <span style={{ color: "#8c8c8c" }}>{children}</span>;
        }
        return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
      },
    }),
    [filenameToChainKey],
  );

  const handleTreeSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length === 0) return;
    const key = selectedKeys[0] as string;
    if (key.startsWith("doc:")) {
      const productCode = key.replace("doc:", "");
      if (selectedDoc?.product_code !== productCode) {
        loadDocDetail(productCode);
      }
    } else if (key.startsWith("chain:")) {
      setSelectedChainKey(key.replace("chain:", ""));
    }
  };

  return (
    <Row gutter={16} style={{ height: "calc(100vh - 140px)" }}>
      {/* Left: Domain list */}
      <Col span={6} style={{ height: "100%", overflow: "auto" }}>
        <Card
          title="产品知识库"
          size="small"
          bodyStyle={{ padding: "8px 0" }}
        >
          {loading ? (
            <Spin style={{ padding: 20, display: "block" }} />
          ) : docs.length === 0 ? (
            <Empty description="知识库为空" style={{ padding: 20 }} />
          ) : (
            <Tree
              treeData={treeData}
              onSelect={(keys) => {
                if (keys.length === 0) return;
                const key = keys[0] as string;
                if (key.startsWith("doc:")) {
                  loadDocDetail(key.replace("doc:", ""));
                }
              }}
              selectedKeys={selectedDoc ? [`doc:${selectedDoc.product_code}`] : []}
              blockNode
              style={{ padding: "0 8px" }}
            />
          )}
        </Card>

        {/* Chain list for selected domain */}
        {selectedDoc && (
          <Card
            title={
              <Space>
                <span>{selectedDoc.name}</span>
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                  {selectedDoc.chunks.length}段
                </Typography.Text>
              </Space>
            }
            size="small"
            bodyStyle={{ padding: "8px 0" }}
            style={{ marginTop: 12 }}
          >
            {detailLoading ? (
              <Spin style={{ padding: 20, display: "block" }} />
            ) : (
              <Tree
                treeData={chainTreeData}
                onSelect={(keys) => handleTreeSelect(keys)}
                selectedKeys={selectedChainKey ? [`chain:${selectedChainKey}`] : []}
                blockNode
                showIcon
                style={{ padding: "0 8px" }}
              />
            )}
          </Card>
        )}
      </Col>

      {/* Right: Markdown content */}
      <Col span={18} style={{ height: "100%", overflow: "auto" }}>
        {detailLoading ? (
          <Card><Spin /></Card>
        ) : selectedChainContent ? (
          <Card
            title={
              <Space>
                <span>{selectedDoc?.name}</span>
                <LinkOutlined />
                <span>{deriveDisplayName(selectedChainKey!)}</span>
                <Tag color={CHAIN_TYPE_META[inferChainType(selectedChainKey)]?.color}>
                  {CHAIN_TYPE_META[inferChainType(selectedChainKey)]?.label}
                </Tag>
              </Space>
            }
            size="small"
            extra={
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {selectedChainChunks.length} 个段落
                {selectedChainChunks[0]?.source_file && (
                  <span> | {selectedChainChunks[0].source_file}</span>
                )}
              </Typography.Text>
            }
          >
            <div style={{ maxHeight: "calc(100vh - 240px)", overflow: "auto", padding: "0 8px" }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {selectedChainContent}
              </ReactMarkdown>
            </div>
          </Card>
        ) : selectedDoc ? (
          <Card>
            <Empty description="请从左侧选择一个文件查看内容" />
          </Card>
        ) : (
          <Card>
            <Empty description="请从左侧选择一个产品域" />
          </Card>
        )}
      </Col>
    </Row>
  );
}
