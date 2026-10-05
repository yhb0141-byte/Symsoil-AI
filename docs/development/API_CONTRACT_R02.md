# R0.2 表达转述与理解核对接口

本合同扩展 R0，不修改正式批准、执行授权或真实数据上线边界。依据本次上传的《共壤社区AI智脑建设与运营实施方案 V1.0》跨语境表达与理解核对章节。仍使用合成数据；模型可选，默认关闭。

## 所有认证读取也需要内存证明

所有认证 API 请求，包括 GET `/auth/me`，均须同时具有 HttpOnly 会话 Cookie 和 `X-CSRF-Token`。令牌仅由显式登录返回并存在页面内存；不能凭 Cookie 单独取回令牌。缺失读取证明返回 401；写入缺失 CSRF 保持 403。登录、注册、公开健康状态不变。退出捕获原令牌请求注销，同时立即清除页面内存；Cookie 残留不再足以直接读取私人 API。实际注销失败仍如实提示服务器未确认，不能声称会话已撤销。

## 新数据对象

保留既有 Utterance 字段，通过新增表扩展，不对已有数据库增加列，不丢弃已有合成资料。时间使用 UTC ISO 格式，ID 为字符串。候选、选择、理解核对均记录来源版本及审计，不记录私人正文到审计。

Candidate 字段：`id, utterance_id, utterance_version, kind, text, context, target_context, purpose, version, origin, confirmed_version, confirmed_at, created_at, updated_at`。`kind` 为 everyday（日常表达）或 discussion（本次讨论表达）；`origin` 为 manual 或 local_model。每个原话当前版本最多各一种候选，共两种。语境由本人主动填写，不取历史私聊，不根据身份推断动机。模型生成建议尚未保存时没有 Candidate ID。

Choice 字段：`utterance_id, utterance_version, version, choice, candidate_id, candidate_version, confirmed_at, updated_at`。choice 为 candidate、original_only、no_rephrase。选择候选必须绑定它的具体版本；另外两种候选字段为 null。每份原话只有一个当前选择。未选择时为 null；第一份 choice_version 为 1。候选确认和原话确认分开，分享不自动发生。

ExpressionDetail：`{utterance: Utterance, candidates: Candidate[], choice: Choice|null, share: {representation:'original'|'candidate',candidate_id:null|string,candidate_version:null|number}|null}`。只返回当前原话版本的候选与选择，仅作者可访问。

Viewpoint 在 R0 字段之外增加 `representation, candidate_id, candidate_version`。只公开本人选择并显式分享的正文、来源版本、作者称呼和确认时间；**不公开私人原话、context、target_context、purpose 或其他未选候选**。representation=original 时 text 为原话，candidate 时为确认转述。候选及选择改变时停止当前分享。

Understanding 字段：`id, topic_id, utterance_id, utterance_version, representation, candidate_id, candidate_version, requester_id, requester_name, author_id, author_name, text, status, correction, version, created_at, updated_at`。status 为 pending、accurate、needs_correction、prefer_in_person。只对听者与表达者本人可见，议题主持人和管理员不能旁观。源观点撤回、改写或分享表示变化后，该核对不再进入当前读取或回应；再次分享同一份完全相同的当前版本可继续访问，不伪造它已被核对。

## 端点

所有写入严格拒绝未知字段。认证和对象 ACL 先于幂等重放；错误版本 409，前提不满足 422，不能访问统一 404。下述要求幂等的动作携带 `Idempotency-Key`，同键异内容 409。

### 表达详情与手写候选

- GET `/utterances/{id}/expression` → ExpressionDetail，仅作者。
- POST `/utterances/{id}/candidates`，body：`{object_version,kind,text,context,target_context,purpose,suggestion_token?}` → ExpressionDetail。text 1–10000，context 最多 3000，target_context 与 purpose 各最多 1000；上下文三个字段允许空字符串但必须显式提供。同原话版本同 kind 已存在则 409，须修改现有候选；不能覆盖另一候选。optional suggestion_token 是服务器签发的真实本地模型来源证明，不是用户可自由填写的 origin；有有效证明且全文及语境未改才记 local_model，无证明记 manual。
- PATCH `/utterances/{id}/candidates/{candidate_id}`，body：`{object_version,candidate_version,text,context,target_context,purpose}` → ExpressionDetail。保留 kind，candidate_version 加一，确认失效；若候选已获确认，清除当前选择及当前分享。origin 改为 manual，表示本人修改。改写私人原话同样使所有旧候选与选择失效。

### 本人选择及确认

- POST `/utterances/{id}/choice`，需幂等。body：`{object_version,choice_version,choice,candidate_id?,candidate_version?}` → ExpressionDetail。choice_version 为当前 Choice.version；没有当前选择时使用 0。candidate 选择必须指定当前源版本候选和具体 candidate_version，记录其 confirmed_version/confirmed_at；另外两种不可夹带非 null 候选字段。选择发生变化即清除当前分享，不能保持旧分享却改变其依据。no_rephrase 表示现有转述不被本人认可，不阻止本人以后主动修改选择或重新请求私人建议。
- 原有 POST `/confirmations` 继续只确认原话。原话与候选的两种确认不混用。分享原话或转述都要求原话当前版本已由本人核对；转述另须对应当前 Choice 和 Candidate 的版本确认。

### 独立分享

- 扩展 POST `/utterances/{id}/share`，仍需幂等。body：`{object_version,topic_id,representation:'original'|'candidate',candidate_id?,candidate_version?,choice_version?}`。省略 representation 默认为 original，兼容原流程。original 不可夹带候选字段；candidate 必须具备三个版本字段，服务器核对 Choice 对应的当前候选。返回 Viewpoint。撤回沿用原端点。
- 分享窗口先选择原话或已确认转述，再预览**实际要发布的唯一正文**与受众。不默默把原话一起发布到议题。议题受众仍为动态成员范围，须保留现有新增参与者提示。
- 原有 topic_detail、幂等 topic 回放过滤及撤回测试扩展为确认转述；旧 share 元数据不能复活已修改或撤下的内容。

### 听者复述与作者核对

- POST `/topics/{topic_id}/understandings`，需幂等。body：`{utterance_id,utterance_version,representation,candidate_id?,candidate_version?,text}`。听者必须是当前议题参与者，源观点必须正在该议题合法展示且所有版本/表示一致；不能给自己提交核对。text 1–5000，为听者亲自填写的“我理解的是……”。只能以该可见观点为依据，不访问私人原话。
- GET `/understandings` → Understanding[]，仅当前调用者是 requester 或 author 且源观点仍有效的记录。不会在 topic_detail 中公开私人理解核对内容。
- POST `/understandings/{id}/response`，需幂等。body：`{object_version,status:'accurate'|'needs_correction'|'prefer_in_person',correction}`。仅 author；needs_correction 必须有非空 correction（最多5000）；其他允许空。pending 才可回应；成功 version 加一，不能由听者或主持人代确认。返回 Understanding。
- 两边可以查看自己的待核对及已回应记录；准确表示听懂，不增减方案立场、任务状态或原话分享权限。

### 可选本地模型建议

- GET `/ai/status` → `{enabled:boolean,available:boolean,provider:'ollama'|null,model:string|null,reason:string}`。认证读取。availability 需检查本地已安装模型，不因配置 enabled 自动报可用；失败返回安全说明，不泄漏凭据或模型正文。
- POST `/utterances/{id}/suggestions`，body：`{object_version,context,target_context,purpose}` → `{utterance_version,candidates:[{kind,text,suggestion_token}],clarifications:string[],provider:'ollama',model:string}`。最多两个不同 kind，澄清问题最多四条。信息不足时可只返回澄清问题和空 candidates；两者均为空时视为无效输出。仅作者，输出为待核对私人建议；**不自动保存、确认或分享**，本人在候选编辑表单中选择保存。
- 每个 suggestion_token 用应用启动时随机密钥 HMAC 签名，仅携带作者、原话ID与版本、kind、完整候选字段规范化摘要和十分钟到期时间，不含私人正文。保存候选时检查签名、作者、来源版本、字段摘要及有效期。编辑正文或任一语境字段后移除 token，明确作为本人改写保存。服务重启会使预览证明失效，用户仍可选择无证明的人工保存；来源证明失效不允许冒记为模型生成。
- 默认 `SYMSOIL_AI_ENABLED=false`。启用须配置 `SYMSOIL_OLLAMA_MODEL`，默认地址 `http://127.0.0.1:11434`；如提供 `SYMSOIL_OLLAMA_URL`，只允许字面 loopback 地址、http、无认证/查询/片段，不允许 DNS、公网、link-local、重定向或环境代理。模型名称不允许 cloud 类型；禁止自动下载、云端回退和工具调用。实际 Ollama 服务须配置 `OLLAMA_NO_CLOUD=1` 并由维护者检查外发防护，应用环境变量不能替代守护进程配置。
- 使用 `/api/chat`，stream=false，严格 JSON schema；输出二次校验，超限、重复 kind、空文本、未知字段或解析错误均失败。只发送当前原话和本人显式给出的三项语境，不读任何其他业务对象。原话和模型正文不写日志。
- 模型调用有明确超时、响应字节上限及单次并发限制。调用期间不持 SQLite 写锁；结束后重新校验会话、账号、作者与源版本，冻结返回401，原话变更409，绝不能用生成前权限放行结果。未启用或模型缺失503，繁忙429，模型不可用不影响人工流程。

## 本轮验收与迁移

旧数据库只增加新表；旧合成账号和原话可继续使用，旧表达分享仍是 original。软件重启后，旧浏览器没有内存证明须重新显式登录。新增表并非生产迁移机制，不以此关闭 R1 的数据库迁移验收。

必测：Cookie-only读阻断；确认转述不分享；候选只有本人可见；分享转述不泄漏原话或语境；原话/候选/选择改动失效；撤回和幂等不能复活；理解核对双方隐私/作者专属回应/拒绝自核对/源撤回阻断；本人纠正不生成支持票；AI disabled、模型缺失、无代理/重定向/云回退、超时/恶意输出、生成中冻结及原话改写；旧合成数据不丢失。
