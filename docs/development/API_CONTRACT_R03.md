# R0.3 资料与引用合同

本轮以 R0.2 为基础，仍为合成开发。实现文字资料的私人录入、指定审核、固定受众发布、关键词目录、原文引用及可选有来源问答。原话、理解、立场、批准、任务事实不变。资料审核仅决定入库，不能赋予正文中的决定效力。

## 状态和存储

只新增表，原 `Document` 不改列。`KnowledgeDocument`（控制）、`KnowledgeRevision`（不可变完整版本）、`KnowledgeAudience`（已发布固定名单）、`KnowledgeReview`（审核记录）分开存储。控制 ID 为稳定 document_id，在私人阶段没有原 Document 行；发布事务才写原 Document 的最新获准快照。目录和计数不得直接全读原 Document。

Control 字段：`id,owner_id,version,latest_revision_id,submitted_revision_id|null,reviewer_id|null,published_revision_id|null,access_epoch,withdrawn_at|null,created_at,updated_at`。内容编辑生成新 revision，控制 version 加一，停止旧送审，不覆盖旧发布版。送审、审核、撤下、收紧受众均加控制 version；发布／撤下／收紧加 access_epoch。草稿、送审和最后发布可分别显示，不能混成同一“已确认”。

Revision 字段：`id,document_id,number,title,category,body,source,rights,purpose,maintainer,effective_until|null,requested_scope:'community'|'members',requested_member_ids:string[],created_at`。正文最多 20000 字；title 1–160、category 1–60、source 1–1000、rights 1–2000、purpose 1–1000、maintainer 1–500。仅收粘贴文字或本地读取 UTF-8 txt/md；不提供二进制上传、OCR、富 HTML、向量索引。effective_until 为带时区 ISO 时间；发布时未过期。

新版本必须完整保存全部字段，服务端拒绝未知字段及身份覆盖。requested_member_ids 在 community 时为空；members 时至少一位当前有效成员，固定名单仅使用明确 ID，不从角色推断。owner 有管理资料权，不能自审。审核人必须为另一个当前有效 facilitator/admin，且只在当前送审的精确版本获得审核读取；管理员没有草稿通读权。未送审新稿不能沿用旧审核人的读取。

已发布资料 community 对当前有效登录成员开放；members 仅名单内成员和作者可读。审核人不因曾审核就获得长期目录权。过期、撤下、失效版本不进入目录、数量、引用或模型上下文。所有无权对象回应 404，不能泄漏标题／片段／存在性。本人编辑新稿时上一有效发布版继续可读，界面清楚说明。

仅已知 R0 seed 合成资料可显式初始化为 legacy community 元数据；未知、缺元数据旧 Document 行默认隔离。seed CLI 必须建立新元数据。不自动选择真实资料的作者或审核人。旧业务账号、表达、邀请保留。

## 接口（/api/v1，认证读写都要求 Cookie 与内存证明）

通用 `KnowledgeDetail`：`{id,version,owner_id,owner_name,latest:Revision,submitted:Revision|null,published:Revision|null,reviewer_id|null,access_epoch,withdrawn_at|null,reviews:Review[]}`，仅作者完整读取；审核人响应不能夹带未送审 latest，审核用专用形状。Revision requested_member_ids 仅作者及当前审核人可见，不放在目录公共摘要中。

| 接口 | 请求与结果 |
| --- | --- |
| GET /knowledge/mine | 作者的 KnowledgeDetail[]；其他人不能旁观 |
| POST /knowledge | Revision 全字段 → KnowledgeDetail，创建私稿，不进入目录 |
| GET /knowledge/{id} | 作者完整详情；其他人404 |
| PATCH /knowledge/{id} | `{object_version,...Revision字段}` → KnowledgeDetail；新增内容版本，不动原发布 |
| GET /knowledge/reviewers | 当前有效 facilitator/admin 的 `{id,display_name}`，排除本人 |
| POST /knowledge/{id}/submit | 幂等；`{object_version,revision_id,reviewer_id,consent:true}` → KnowledgeDetail；授权此精确版本给指定审核人 |
| GET /knowledge/reviews | 只返回当前本人审核队列：`{id,version,owner_id,owner_name,revision:Revision}`[]，无其他私人版本 |
| POST /knowledge/{id}/review | 幂等；`{object_version,revision_id,decision:'approve'|'changes_requested',reason}`；退回理由1–2000，通过允许空理由；仅指定审核人，作者不可代确认。返回 `{ok:true,id,version,decision}`，不夹带草稿 |
| POST /knowledge/{id}/withdraw | 幂等；`{object_version}` → KnowledgeDetail；立即停止现发布版访问，保留私人历史 |
| POST /knowledge/{id}/restrict | 幂等；`{object_version,scope:'members',member_ids}` → KnowledgeDetail；只能从community收为固定名单，或删除现名单成员，不允许扩大。空名单可仅作者访问。无发布则422 |
| GET /documents?q= | 保留旧目录形状，扩展发布元数据和 snippets；仅当前可读、未过期发布版；q<=200，匹配标题／正文 literal keyword，转义 LIKE |
| GET /documents/{id}?revision_id= | 当前可读精确发布版全文与来源；无效版本404，query可省略取当前版 |
| POST /knowledge/answers | `{question,use_model:false}` → KnowledgeAnswer，question1–200；只检索当前获准资料，默认返回明确标记资料摘录；use_model=true 调用可选 Ollama，默认关503，无伪造成功 |

发布目录 `PublishedDocument` 保留 `id,title,category,body,version,source,updated_at`，增加 `revision_id,owner_name,maintainer,purpose,effective_until,scope,access_epoch,snippets`。snippets：`{citation_id,quote,start_line,end_line}`，片段来自真实正文，最多3段各800字。外部来源作为纯文本，不自动获取或生成裸下载链接。`version` 是内容 number，控制 version 单独使用。旧端点返回body仅因调用者当前获准，数量同样过滤。

`KnowledgeAnswer`：`{mode:'extract'|'local_model'|'insufficient',answer:string,citations:Citation[],provider:null|'ollama',model:string|null}`。Citation：`{citation_id,document_id,revision_id,document_version,title,source,quote,start_line,end_line,access_epoch}`。服务器生成引用与定位，不接受模型创建URL。无匹配返回 insufficient 和明确无足够依据，不能用普通世界知识回答业务状态或现行决定。摘录模式明确“资料摘录，非模型回答”，不包装为推理。回答不写入数据库或日志。

问答检索可使用简单中文二字词与英文词关键词评分，固定上限最多5份资料、每份3段，仅供小型开发目录，不宣称语义/向量检索或真实质量已验收。模型仅接收当前已鉴权片段、问题与有限来源ID；schema为 `{answer,citation_ids}`，最多6个不同ID且均来自本次候选。非空答案必须带有效引用；未知ID、重复ID、无引用、超限输出503。引用的标题、位置和quote由服务器重建。

模型在返回前重新检查会话、账号、每份来源 published_revision_id/access_epoch/有效期以及访问权限；源撤下、取代、受众变化返回409，账号冻结401。生成期间释放数据库锁，完整结果校验后一次返回；不流式外发私有内容。沿用 loopback、禁代理／重定向／下载／云回退、60秒可取消整体HTTP时限和单并发门。资料是待引用的数据，其指令不取得执行权限。

## 验收和边界

必测私人标题／正文／数量隔离、指定审核精确版本及禁止自审、版本与幂等不复活、固定名单搜索／引用／计数隔离、发布新版本后旧引用失效、收紧／撤下／有效期、模型源变化／账号冻结、伪造引用拒绝、旧库增表保留、模型关闭人工路径。本人资料管理列表在改写／撤下后同步当前发布与问答视图；旧异步结果不得回灌新会话。已被用户看见的资料无法从其记忆或另存副本收回。

R0.3 不交付完整二进制资料管道、历史公开浏览、纠错工单、模型质量、完整权限日志、生产迁移恢复、正式社区上线。审核规则由人工和社区确定，role只是开发中明确指定审核人的资格基础。
