# R0.4 私人资料纠错合同

基线 R0.3 `5289f765199727259d0d84bfc03048aa2da685f7`。本轮只做 F02 的双方私有纠错，不是完整 F11 工单系统；依旧合成开发。

## 事实和权限

资料录入者账号为唯一接收人，由服务器从 KnowledgeDocument.owner_id 得出。自由文本 maintainer 只作人工联系说明，不充当可验证账号。创建必须由当前有权读精确发布版的另一成员主动预览并 consent=true；双方账号有效，revision_id、access_epoch 和 expected_recipient_id 均匹配。预览不会发送请求。

只新增 KnowledgeCorrection 表，不改旧表列。字段：id、document_id、revision_id、document_version、source_access_epoch、requester_id、recipient_id、text、response|null、status(submitted/responded/withdrawn)、version、created_at、updated_at、responded_at|null、withdrawn_at|null。不复制源标题、正文或引用片段，不把纠错内容放进目录、问答上下文、公共日志或资料版本。

双方可读本人明确分享的问题及回应，管理员、主持人和审核人无额外权限。双方交流的授权独立于源资料：源被撤下、取代或收紧后，既有交流保留，但源信息每次重新鉴权，无法读取关联精确版本时 source=null，不能自动绑定新版。请求者可在提交或回应后撤回共享：本人保留历史，收件人列表、计数、详情、旧键重放立即停止提供内容。已看见或另存的副本无法追回。

只有接收人可在 submitted 状态回应一次，必须主动确认发给请求者；responded 仅为“已回应”，不代表资料已纠正。若需修订，通过本人资料管理另存完整新版本，再独立送审。请求不自动改资料、批准、分享、立场或任务。冻结账号本人401；新提交和新回应也检查对方有效，已有分享不因对方冻结自动撤销。

## 接口

认证读写沿用 Cookie + 页面内存证明。所有写入有 Idempotency-Key；更新还需 object_version。身份、对象可见性在重放前检查；缓存只保存请求ID，重建当前详情，绝不恢复 withdrawn。创建锁定资料控制行并重核发布/受众；回应、撤回用CAS，旧版本409。

| 接口 /api/v1 | 合同 |
| --- | --- |
| GET /documents/{id}/correction-context?revision_id=...&access_epoch=... | 当前精确资料预览：{document_id,revision_id,document_version,access_epoch,title,maintainer,recipient:{id,display_name}}；无权/旧版本404，旧epoch409，自身或接收人不可用422 |
| POST /knowledge-corrections | {document_id,revision_id,access_epoch,expected_recipient_id,text,consent:true} → Correction；text普通非空文字1–2000，拒绝未知及身份覆盖字段 |
| GET /knowledge-corrections | {items:Correction[],counts:{sent,incoming,pending_incoming}}；只本人已发或当前仍获授权的收到请求 |
| GET /knowledge-corrections/{id} | 当前本人可见 Correction；其他人404 |
| POST /knowledge-corrections/{id}/respond | {object_version,text,consent:true} → Correction；仅接收人，submitted→responded |
| POST /knowledge-corrections/{id}/withdraw | {object_version} → Correction；仅请求者，submitted/responded→withdrawn |

Correction：{id,document_id,revision_id,document_version,source_access_epoch,requester_id,requester_name,recipient_id,recipient_name,text,response,status,version,created_at,updated_at,responded_at,withdrawn_at,source:null|{document_id,revision_id,document_version,access_epoch,title}}。source只包含当前仍能读的同一精确版本，绝不包含整篇资料。角色与收件人不可由客户端覆盖。

## 交互及验收

从精确原文窗口“提出资料纠错”重新获取预览，用户填写问题，核对接收人、版本和仅双方范围后才发送。资料页增加“纠错请求”，已发/收到及待回应数只来自本人范围。打开详情再次读取，原文仍走现行精确版本API。接收人手写回应并确认；作者可打开本人的资料管理，再另存新版本。请求者预览撤回后主动提交。页面、账号切换和较早请求不得回填旧正文。

验证精确版本/epoch、伪收件人、自发、未知字段、双人隔离、撤回后缓存不复活、源失效时标题不泄漏、冻结、并发回应/撤回、操作不改变知识/议题/任务、增表保留旧库，以及桌面和手机实际浏览器。
