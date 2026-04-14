# 传统服务器部署指南（CentOS 7）

本文档描述如何在 CentOS 7 服务器上部署 Test Knowledge Base 系统。

架构：**Nginx（前端静态 + 反向代理）→ FastAPI（uvicorn 单 worker）→ PostgreSQL**

> **前端构建策略：** CentOS 7 的 glibc 2.17 无法运行 Node 18+，而项目的 TypeScript 5.8 要求 Node >= 18。因此前端在本地电脑构建，将 `dist/` 目录上传到服务器。

---

## 1. 服务器环境准备

### 基础工具

```bash
sudo yum install -y epel-release curl git gcc make rsync
sudo yum install -y nginx
```

### 安装 Python 3.11

CentOS 7 官方源和 IUS 源均不提供 Python 3.11 包，需从源码编译。
Python 3.11 要求 OpenSSL >= 1.1.1，而 CentOS 7 自带 OpenSSL 1.0.2，因此需先编译 OpenSSL 1.1.1。

**第一步：编译 OpenSSL 1.1.1**

```bash
sudo yum install -y perl-core zlib-devel
cd /tmp
curl -O https://www.openssl.org/source/openssl-1.1.1w.tar.gz
tar xzf openssl-1.1.1w.tar.gz
cd openssl-1.1.1w
./config --prefix=/usr/local/openssl-1.1.1 --openssldir=/usr/local/openssl-1.1.1 shared zlib
make -j$(nproc)
sudo make install
# 验证
/usr/local/openssl-1.1.1/bin/openssl version
# 应输出 OpenSSL 1.1.1w
```

**第二步：编译 Python 3.11**

```bash
sudo yum install -y bzip2-devel libffi-devel zlib-devel readline-devel sqlite-devel xz-devel
cd /tmp
curl -O https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz
tar xzf Python-3.11.9.tgz
cd Python-3.11.9
./configure \
    --enable-optimizations \
    --prefix=/usr/local \
    --with-openssl=/usr/local/openssl-1.1.1 \
    --with-openssl-rpath=auto
make -j$(nproc)
sudo make altinstall
```

> `make altinstall` 不会覆盖系统自带的 python/python3，安全。

**验证：**

```bash
/usr/local/bin/python3.11 --version
# 应输出 Python 3.11.9
/usr/local/bin/python3.11 -c "import ssl; print(ssl.OPENSSL_VERSION)"
# 应输出 OpenSSL 1.1.1w
```

### 配置防火墙

```bash
# 确保 firewalld 已安装并运行
sudo yum install -y firewalld
sudo systemctl enable --now firewalld
```

### 配置 SELinux

CentOS 7 默认启用 SELinux（Enforcing 模式）。需要配置以下规则，否则 Nginx 反向代理和静态目录会被拦截：

```bash
# 安装 SELinux 管理工具
sudo yum install -y policycoreutils-python

# 允许 Nginx 向后端发起网络连接（反向代理必须）
sudo setsebool -P httpd_can_network_connect 1

# 预注册前端静态目录的 SELinux 标签（目录会在后续步骤创建）
# restorecon 在前端上传后执行（见第 6 步）
sudo semanage fcontext -a -t httpd_sys_content_t "/opt/smart-test-kb/frontend/dist(/.*)?"
```

> 如果你确认 SELinux 是 Disabled 状态（`getenforce` 输出 Disabled），可跳过此步。

---

## 2. PostgreSQL 配置

```bash
# 安装 PostgreSQL 15
sudo yum install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-7-x86_64/pgdg-redhat-repo-latest.noarch.rpm
sudo yum install -y postgresql15-server postgresql15
sudo /usr/pgsql-15/bin/postgresql-15-setup initdb
sudo systemctl enable --now postgresql-15
```

### 修改认证方式

```bash
sudo vi /var/lib/pgsql/15/data/pg_hba.conf
```

找到这两行，把 `peer` 和 `ident` 改成 `md5`：
```
local   all   all                 peer    →  md5
host    all   all   127.0.0.1/32  ident   →  md5
```

```bash
sudo systemctl restart postgresql-15
```

### 建库建用户

```bash
sudo -u postgres /usr/pgsql-15/bin/psql <<'SQL'
CREATE USER testkb WITH PASSWORD '改成你自己的强密码';
CREATE DATABASE test_knowledge_base OWNER testkb;
SQL
```

### 备份策略

```bash
sudo mkdir -p /var/backups/testkb/uploads
```

创建 `/etc/cron.d/testkb-backup`：

```cron
0 2 * * * postgres /usr/pgsql-15/bin/pg_dump -Fc test_knowledge_base > /var/backups/testkb/db-$(date +\%Y\%m\%d).dump
0 3 * * * root rsync -a /opt/smart-test-kb/backend/uploads/ /var/backups/testkb/uploads/
0 4 * * * root find /var/backups/testkb/ -name "db-*.dump" -mtime +30 -delete
```

---

## 3. 代码部署

```bash
sudo mkdir -p /opt/smart-test-kb
sudo chown $(whoami):$(whoami) /opt/smart-test-kb
cd /opt/smart-test-kb
git clone 你的仓库地址 .

# uploads 目录需要运行用户可写（后端以 nobody 身份运行）
mkdir -p /opt/smart-test-kb/backend/uploads
sudo chown nobody:nobody /opt/smart-test-kb/backend/uploads
```

---

## 4. 环境变量管理

密钥放在代码目录之外，由 systemd EnvironmentFile 加载：

```bash
sudo mkdir -p /etc/smart-test-kb
sudo cp /opt/smart-test-kb/deploy/backend.env.example /etc/smart-test-kb/backend.env
sudo chmod 600 /etc/smart-test-kb/backend.env
sudo chown root:root /etc/smart-test-kb/backend.env
```

编辑 `/etc/smart-test-kb/backend.env`：

```bash
sudo vi /etc/smart-test-kb/backend.env
```

**必须修改的配置项：**
- `DATABASE_URL=postgresql+psycopg://testkb:你的密码@localhost:5432/test_knowledge_base`
- `CORS_ORIGINS=`（留空或不设置，即不启用 CORS 中间件；同域反代不需要 CORS）
- `APP_ENV=production`
- 所有 `LLM_PROVIDER_*_API_KEY=` 填入真实 key

---

## 5. 后端部署

```bash
cd /opt/smart-test-kb/backend
/usr/local/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### systemd unit

```bash
sudo tee /etc/systemd/system/testkb-backend.service > /dev/null <<'EOF'
[Unit]
Description=Test Knowledge Base Backend
After=postgresql-15.service
Requires=postgresql-15.service

[Service]
Type=simple
User=nobody
Group=nobody
WorkingDirectory=/opt/smart-test-kb/backend
EnvironmentFile=/etc/smart-test-kb/backend.env
ExecStart=/opt/smart-test-kb/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now testkb-backend
```

> **单 worker 说明：** 当前启动阶段包含 schema migration、interrupted task recovery、knowledge base sync，这些逻辑未做分布式锁。先用单 worker 上线，等这些启动任务拆出去后再开多 worker。

验证后端启动：

```bash
until curl -sf http://127.0.0.1:8000/health/ready > /dev/null; do sleep 1; echo "等待后端就绪..."; done
echo "后端已就绪！"
```

---

## 6. 前端构建与上传

**在你本地电脑执行**（不是服务器上）：

```bash
cd frontend
npm ci
npm run build
# 产物在 dist/ 目录
```

**上传到服务器：**

```bash
# 用 rsync 上传（--delete 确保不会嵌套或残留旧文件）
rsync -av --delete dist/ root@你的服务器IP:/opt/smart-test-kb/frontend/dist/
```

上传后在服务器上刷新 SELinux 标签：

```bash
sudo restorecon -Rv /opt/smart-test-kb/frontend/dist
```

---

## 7. Nginx 配置

CentOS 7 的 Nginx 配置文件在 `/etc/nginx/conf.d/` 下：

```bash
sudo tee /etc/nginx/conf.d/testkb.conf > /dev/null <<'EOF'
server {
    listen 80 default_server;
    server_name _;

    client_max_body_size 50m;

    # 前端静态文件
    root /opt/smart-test-kb/frontend/dist;
    index index.html;

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
    }

    # 上传文件
    location /uploads/ {
        proxy_pass http://127.0.0.1:8000/uploads/;
    }

    # 健康检查（供外部探针使用）
    location /health/ready {
        proxy_pass http://127.0.0.1:8000/health/ready;
    }

    # 前端路由 fallback（SPA）
    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF

# 移除默认配置避免冲突
sudo mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.bak 2>/dev/null || true

# 检查 /etc/nginx/nginx.conf 是否还有默认 server 块
# 如果有，注释掉或删除其中的 server { ... } 块，只保留 http { ... } 框架
# 可用以下命令查看完整配置：
sudo nginx -T | grep -n "listen\|server_name\|default_server"
# 确保只有 testkb.conf 里的 server 块在监听 80 端口

sudo nginx -t && sudo systemctl enable --now nginx
```

### 开放防火墙端口

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --reload
```

---

## 8. 验证

在浏览器访问 `http://你的服务器IP`，应该能看到前端页面。

```bash
# 在服务器上也可以手动验证
curl -s http://127.0.0.1:8000/health         # 应返回 {"status":"ok"}
curl -s http://127.0.0.1:8000/health/ready    # 应返回 {"status":"ready"}
curl -s http://127.0.0.1/api/projects         # 通过 Nginx 测试 API
```

---

## 9. 健康检查说明

| 端点 | 用途 | 配给谁 |
|------|------|--------|
| `/health` | **Liveness** — 进程是否活着 | systemd watchdog / 内部监控 |
| `/health/ready` | **Readiness** — 启动完成且 DB 可达 | 外部监控探针 / 手动验证 |

**不要混用。** Liveness 始终返回 200（只要进程在）；Readiness 在启动阶段返回 503，完成后检查 DB 连通性。

> **注意：** 当前 Nginx 配置本身并不会根据 readiness 状态自动拦截 `/api/` 请求。`/health/ready` 的作用是提供给外部监控探针或手动验证使用。如果需要真正的流量门控，需要在部署脚本中先检查 readiness 再启动 Nginx。

---

## 10. 初始化阶段说明

后端启动分两个阶段：

### 阶段 1：import-time（模块加载时）
- `Base.metadata.create_all()` — 建表
- `ensure_*` 系列函数 — schema migration

这些在 Python 导入模块时就执行，早于 readiness 检查覆盖范围。如果这里失败，进程直接起不来（systemd 会按 RestartSec 重试）。

### 阶段 2：runtime startup（FastAPI startup event）
- 恢复中断的 RuleTreeSession / RiskAnalysisTask / NormalizedRequirementDocTask
- 同步 knowledge_base/products/ 到数据库
- 设置 `app.state.ready = True`

在阶段 2 完成之前，`/health/ready` 返回 503。

---

## 11. 启动顺序

```
PostgreSQL 启动
    ↓
testkb-backend 启动（systemd After=postgresql-15.service）
    ↓ import-time: create_all + migrations
    ↓ startup event: recover + sync + ready=True
    ↓
确认 readiness（curl /health/ready 返回 200）
    ↓
Nginx 启动（或 reload）开始接流量
```

> **部署脚本建议：** 在 systemctl start testkb-backend 之后、systemctl reload nginx 之前，加一个循环检查：
> ```bash
> until curl -sf http://127.0.0.1:8000/health/ready > /dev/null; do sleep 1; done
> ```

---

## 12. 常用运维命令

```bash
# 查看后端状态
sudo systemctl status testkb-backend
sudo journalctl -u testkb-backend -f

# 重启后端
sudo systemctl restart testkb-backend

# 更新代码后（在服务器上）
cd /opt/smart-test-kb
git pull
cd backend && source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart testkb-backend
until curl -sf http://127.0.0.1:8000/health/ready > /dev/null; do sleep 1; done
sudo systemctl reload nginx

# 更新前端（在本地电脑构建后上传）
# 本地: cd frontend && npm ci && npm run build
# 本地: rsync -av --delete dist/ root@服务器IP:/opt/smart-test-kb/frontend/dist/
# 服务器: sudo restorecon -Rv /opt/smart-test-kb/frontend/dist
# 服务器: sudo systemctl reload nginx

# 手动检查 readiness
curl -s http://localhost:8000/health/ready | python3 -m json.tool

# 数据库手动备份
sudo -u postgres /usr/pgsql-15/bin/pg_dump -Fc test_knowledge_base > ~/db-backup.dump

# 数据库恢复
sudo -u postgres /usr/pgsql-15/bin/pg_restore -d test_knowledge_base ~/db-backup.dump
```

