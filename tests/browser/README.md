# R0.2 真实浏览器流程

此测试启动临时 SQLite 合成库和本机 API，用三个独立浏览器会话操作真实网页，运行完成后删除临时库。请先完成根 README 的依赖安装和前端构建。测试使用本机 8000 端口，不能与另一个服务同时占用。

本轮使用 Playwright 1.51.1 与其 Chromium 134.0.6998.35；它们只属于测试环境，不随应用交付。可在独立临时目录安装该测试版本：

```bash
npm install --prefix /tmp/symsoil-browser-qa playwright@1.51.1
node /tmp/symsoil-browser-qa/node_modules/playwright/cli.js install chromium
read -rs SYMSOIL_DEMO_PASSWORD
export SYMSOIL_DEMO_PASSWORD
SYMSOIL_PLAYWRIGHT_MODULE=/tmp/symsoil-browser-qa/node_modules/playwright/index.mjs \
  .venv/bin/python tests/browser/run.py
unset SYMSOIL_DEMO_PASSWORD
```

使用至少 12 字符的合成测试口令，不使用真实账号密码。如已安装其他 Playwright 环境，可通过 `SYMSOIL_PLAYWRIGHT_MODULE` 指向其模块文件，并记录对应浏览器版本。Linux 缺少浏览器运行库时，按 Playwright 环境要求安装系统依赖。

设置 `SYMSOIL_TEST_ARTIFACTS` 为测试环境的绝对目录可保存截图；截图仅包含合成资料。不要把真实社区截图或数据库提交到公开仓库。

默认脚本八组流程涵盖资料来源、确认与分享隔离、跨成员观点、编辑失效、方案立场、邀请协商／拒绝／接受、注册与冻结、手机与退出。脚本还拒绝浏览器异常、页面水平溢出及外域资源请求。当前结果见 `docs/development/VALIDATION_R02.md`。

设置 `SYMSOIL_BROWSER_SCRIPT=tests/browser/security.mjs` 可复跑独立的六组安全界面检查，包括延迟退出竞态、断网退出后显式登录、字段校验、模拟时钟的活跃／闲置处理，以及残留 Cookie 无页面内存证明时认证读取返回 401。断网退出仍不等于服务端会话已注销。

设置 `SYMSOIL_BROWSER_SCRIPT=tests/browser/expressions.mjs` 复跑七组跨语境表达流程：两种私人候选、独立唯一正文分享、双方理解与作者修正、候选及原话版本失效、新版原话主动分享与撤回、390 像素手机弹窗、默认关闭模型。原话、语境、未选候选及双方核对不得出现在其他人的议题响应中。

另加 `SYMSOIL_TEST_AI_FIXTURE=1` 运行相同表达脚本，会在 127.0.0.1:11435 启动**合成 Ollama HTTP 协议服务**，调用真实适配器，验证建议只预览、来源证明、手工修改后记为人工。此服务只在测试运行器的显式开关下启动，不是生产兜底，不运行模型权重，不证明真实模型能力或性能。

```bash
SYMSOIL_BROWSER_SCRIPT=tests/browser/expressions.mjs \
  SYMSOIL_TEST_AI_FIXTURE=1 \
  SYMSOIL_PLAYWRIGHT_MODULE=/tmp/symsoil-browser-qa/node_modules/playwright/index.mjs \
  .venv/bin/python tests/browser/run.py
```

CI 默认运行后端与前端单元检查；此浏览器流程在本轮开发环境单独运行，尚未加入 CI 浏览器矩阵。
