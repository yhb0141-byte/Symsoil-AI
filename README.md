# 共壤 SymSoil AI

由社区掌握的本地协作工作台，帮助成员表达、核对彼此理解、讨论不同方案并形成清楚的行动约定。

当前版本为 **R0.2 合成数据开发版**。在本地工作台上增加候选转述、本人选择和听者理解核对，并提供默认关闭的 Ollama 本机适配器。真实模型权重与翻译质量、正式决定批准、共同记忆发布和完整备份恢复仍需后续验收。

## 当前功能

- 手机与桌面的中文工作台、待回应事项和六个业务入口。
- 本地账号、一次性注册邀请、会话退出、管理员冻结。
- 私人原话、本人准确性确认、显式分享、修改后重新确认与撤回。
- 最多两种私人候选转述、本人修改／确认／拒绝／仅保留原话，分享前预览唯一正文。
- 听者填写复述，原说话者核对准确、提出修正或选择当面交流；核对内容仅双方可见。
- 可选本机 Ollama 表达建议，真实模型缺失时显示不可用，手工候选仍能完成流程。
- 指定参与者的议题、方案比较、支持／有条件支持／保留／反对／需要了解。
- 合成项目内的任务邀请、本人接受、拒绝和提出条件。
- 合成资料目录与关键词查询，个人操作记录。

确认表达准确不自动分享，理解准确不表示赞同，同意方案不自动接受任务，未回应不等于支持。只分享转述时，私人原话和补充背景不会一起进入议题。账号管理员也不能因此读取他人的私人草稿。

## 本地运行

需要 Python 3.12 和 Node.js 22.12 或更高版本。以下命令在仓库根目录执行。第一次安装依赖需要联网，安装与构建完成后的本地应用不需要外部字体、脚本或云端身份服务。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r services/api/requirements.txt
npm --prefix apps/web ci
npm --prefix apps/web run build
./scripts/seed-demo.sh
./scripts/start.sh
```

打开 http://127.0.0.1:8000 。初始化脚本会让你设置本机演示口令，合成账号为 `admin`、`lin`、`qiao`。只对空数据库初始化，不重置已有口令。演示口令由本机运行者设置，不包含在仓库里。

默认数据位于 `data/symsoil.db`，仅供开发验证。`start.sh` 只启动已有构建，不安装或下载依赖。`dev.sh` 用于开发时重新安装依赖及构建。任务接受发生在合成项目中，不构成真实社区决定或实际资源使用授权。

已有 R0 合成数据库可继续使用，本轮只增加表，不重置账号或原话。刷新后需显式登录；所有认证读取同时要求 Cookie 和仅存在页面内存中的证明，残留 Cookie 单独无法读取私人 API。生产数据迁移仍未交付。

### 可选本地表达模型

人工流程无需模型。已有本机 Ollama 与本地模型时，可以按 [本地模型说明](docs/development/LOCAL_MODEL.md) 显式启用。服务只连接字面回环地址，无云端回退或自动下载。模型建议先为私人预览，保存后由本人核对，不能自动代表社区或发布观点。

### 开发时前后端分开运行

```bash
PYTHONPATH=services/api .venv/bin/python -m uvicorn symsoil_api.main:app --host 127.0.0.1 --port 8000 --reload
npm --prefix apps/web run dev
```

Vite 将 `/api` 请求代理到本地后端。开发源地址通过 `SYMSOIL_ALLOWED_ORIGINS` 精确限定；如使用其他端口，显式配置该列表。环境项见 [.env.example](.env.example)，应用以进程环境变量读取配置，不自动把模板文件当作真实配置。

### Docker

```bash
docker compose build
docker compose run --rm -e SYMSOIL_DEMO_PASSWORD app python -m symsoil_api.cli seed --demo
docker compose up -d
```

先在当前终端设置 `SYMSOIL_DEMO_PASSWORD` 为至少 12 字符的临时演示口令，不使用真实服务口令。Compose 默认只绑定本机 127.0.0.1，数据使用独立卷。容器配置为开发配置；开放局域网和真实试用前，需完成 HTTPS、真实账号及相应验收。Compose 未编排模型服务。Docker 构建验证状态见 [R0.2 验证记录](docs/development/VALIDATION_R02.md)。

## 测试

```bash
.venv/bin/python -m pip install -r services/api/requirements-dev.txt
./scripts/check.sh
```

后端测试覆盖对象权限、读取证明、CSRF、账号冻结、版本冲突、原话／转述分享、理解核对双方权限及幂等。前端进行领域规则测试、TypeScript 类型检查与生产构建；[浏览器流程](tests/browser/README.md) 走实际 API 和数据库路径。模型协议测试使用明确标记的合成服务，不代表真实模型质量。结果及未验收项目见 [R0.2 验证记录](docs/development/VALIDATION_R02.md)。

## 产品与工程文档

| 文件 | 用途 |
| --- | --- |
| [产品书](docs/product/PRD.md) | 完整产品需求、交互、权限和验收标准 |
| [开发任务清单](docs/development/BACKLOG.md) | 20 项工作、依赖及交付要求 |
| [R0 范围](docs/development/R0_SCOPE.md) | 上一轮基线及限制 |
| [R0.2 范围](docs/development/R02_SCOPE.md) | 表达、理解核对及会话证明增量 |
| [API 合同](docs/development/API_CONTRACT.md) | 前后端接口、数据形状和关键写入规则 |
| [R0.2 API 合同](docs/development/API_CONTRACT_R02.md) | 候选版本、本人选择、分享与模型预览 |
| [实施方案对照](docs/product/IMPLEMENTATION_ALIGNMENT.md) | 上传方案与实际交付的对应及差异 |
| [架构决定](docs/adr/0001-r0-local-modular-application.md) | 本地模块化应用、数据库与 AI 边界 |
| [运行与交接](docs/development/OPERATIONS.md) | 本机操作、停止、备份边界与逐项签收 |

## 数据和运行边界

仓库公开的是软件与方法，运行中的成员资料、账号口令、数据库、模型权重和备份不进入 Git。R0 不处理真实敏感资料；正式试用需落实责任人、参与说明、批准程序和运营能力。

SQLite 用于低门槛开发。后端保留 PostgreSQL 连接能力，生产迁移及恢复仍需专项验证。无模型时人工流程可以继续；数据库或授权服务不可用时，界面不能把本地显示误报为已提交。

当前未指定开源许可证。对外开源及自研成果的许可方式由项目方决定，第三方组件遵循其各自许可。
