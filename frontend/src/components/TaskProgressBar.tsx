import type { CSSProperties, ReactNode } from "react";
import { Alert, Progress, Space, Typography } from "antd";

export type TaskStatus = "idle" | "pending" | "running" | "success" | "error" | "done";

export interface TaskProgressStep {
  key: string;
  label: string;
  status: TaskStatus;
  description?: string;
}

export interface TaskProgressBarProps {
  title?: ReactNode;
  description?: ReactNode;
  percent?: number;
  status?: TaskStatus;
  message?: ReactNode;
  steps?: TaskProgressStep[];
  /** 是否折叠为小型提示条（紧凑模式） */
  compact?: boolean;
  style?: CSSProperties;
  /** 右上角额外操作（如取消） */
  extra?: ReactNode;
  /** 指示任务无法预估进度时显示 indeterminate 进度 */
  indeterminate?: boolean;
}

function resolveAlertType(status: TaskStatus) {
  switch (status) {
    case "error":
      return "error" as const;
    case "success":
    case "done":
      return "success" as const;
    case "running":
    case "pending":
      return "info" as const;
    default:
      return "info" as const;
  }
}

function resolveProgressStatus(status: TaskStatus) {
  if (status === "error") return "exception" as const;
  if (status === "success" || status === "done") return "success" as const;
  if (status === "running" || status === "pending") return "active" as const;
  return "normal" as const;
}

export default function TaskProgressBar({
  title,
  description,
  percent,
  status = "idle",
  message,
  steps,
  compact = false,
  style,
  extra,
  indeterminate = false,
}: TaskProgressBarProps) {
  const displayedPercent = indeterminate
    ? status === "success" || status === "done"
      ? 100
      : status === "error"
      ? 100
      : percent ?? 30
    : percent ?? 0;

  return (
    <div style={{ width: "100%", ...style }}>
      <Alert
        type={resolveAlertType(status)}
        showIcon
        banner={compact}
        message={
          <Space size={8} align="center" wrap>
            {title ? <Typography.Text strong>{title}</Typography.Text> : null}
            {message ? <Typography.Text type="secondary">{message}</Typography.Text> : null}
          </Space>
        }
        description={
          compact ? null : (
            <Space direction="vertical" size={6} style={{ width: "100%" }}>
              {description ? <Typography.Text type="secondary" style={{ fontSize: 12 }}>{description}</Typography.Text> : null}
              <Progress
                percent={displayedPercent}
                status={resolveProgressStatus(status)}
                size="small"
                showInfo={!indeterminate || status === "success" || status === "done" || status === "error"}
              />
              {steps && steps.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {steps.map((step) => (
                    <div key={step.key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <StepDot status={step.status} />
                      <Typography.Text
                        style={{ fontSize: 12 }}
                        type={step.status === "error" ? "danger" : step.status === "success" || step.status === "done" ? undefined : "secondary"}
                      >
                        {step.label}
                      </Typography.Text>
                      {step.description ? (
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                          {step.description}
                        </Typography.Text>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </Space>
          )
        }
        action={extra}
      />
    </div>
  );
}

function StepDot({ status }: { status: TaskStatus }) {
  const color =
    status === "success" || status === "done"
      ? "#52c41a"
      : status === "error"
      ? "#ff4d4f"
      : status === "running"
      ? "#1677ff"
      : status === "pending"
      ? "#faad14"
      : "#d9d9d9";
  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
      }}
    />
  );
}
