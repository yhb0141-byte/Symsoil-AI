# R0 implementation contract

This is the original R0 endpoint baseline. [R0.2 additions](API_CONTRACT_R02.md) override authentication reads and extend expression/sharing flows; use both documents together.

All endpoints use `/api/v1`. JSON errors: `{detail: string}`. Authentication requires a Cookie plus the in-memory `X-CSRF-Token` on **all** authenticated requests, including GET. Only explicit `POST /auth/login` bootstraps `{user, csrf_token}`; `GET /auth/me` returns that shape only when the caller already supplies the proof. Send `Idempotency-Key` on confirm, share, stance, invitation response, expression choice, and understanding actions. No browser persistent auth token.

User: `{id, username, display_name, role, active}`. Roles: admin, facilitator, member. IDs are strings. UTC ISO timestamps.

| Endpoint | Request | Response |
| --- | --- | --- |
| POST /auth/login | username,password | user,csrf_token |
| GET /auth/me | none | user,csrf_token |
| POST /auth/logout | none | ok |
| GET /dashboard | none | counts:{topics,open_invitations,utterances,documents},pending:Invitation[],topics:Topic[],ai:{available:false},release:{stage:'R0',synthetic:true} |
| GET /documents | optional q | Document[] |
| GET /utterances | none | own Utterance[] |
| POST /utterances | text,title | Utterance |
| PATCH /utterances/{id} | text,title,object_version | Utterance; new version unconfirmed |
| POST /utterances/{id}/confirmations | object_version | Utterance; no sharing |
| POST /utterances/{id}/share | object_version,topic_id | shared viewpoint; explicit original-text sharing for R0 |
| POST /utterances/{id}/revoke | object_version | Utterance; blocks topic reads immediately |
| GET /topics | none | Topic[] accessible to member |
| POST /topics | title,description,scope | Topic; creator facilitator; topic limited to invited participants |
| GET /topics/{id} | none | TopicDetail |
| POST /topics/{id}/participants | member_id,object_version | TopicDetail; owner only |
| POST /topics/{id}/options | title,description,cost,labor,risks,object_version | TopicDetail; topic participant |
| POST /topics/{id}/stances | option_id,option_version,stance,condition | TopicDetail; member stance, no approval |
| GET /members | none | member directory of id,display_name; synthetic community directory |
| GET /invitations | none | invitations caller receives or issued |
| POST /topics/{id}/invitations | invitee_id,title,description,completion_criteria,resources,compensation,due_date | Invitation; owner only; R0 synthetic independent task |
| POST /invitations/{id}/response | object_version,response:'accepted'|'declined'|'negotiating',note | Invitation; recipient only |
| GET /auth/sessions | none | safe session status for current member |
| GET /audit | none | caller's events only |
| POST /admin/invites | username,display_name,role | one-time invitation `{token,expires_at}`; admin only |
| POST /auth/register | token,password | user; single-use, valid invitation required |
| GET /admin/members | none | users; admin only |
| POST /admin/members/{id}/freeze | none | ok; invalidate sessions |
| GET /health | none | status,stage,ai_available; no private counts |

Utterance: `{id,title,text,version,confirmed_version,confirmed_at,shared_topic_id,created_at,updated_at}`. Only author reads original; published topic viewpoints separately have `{id,author_id,author_name,text,utterance_version,confirmed_at}` and only expose the explicitly shared version. Revocation or a new original version removes it from current topic views. A facilitator cannot read a private draft.

Document: `{id,title,category,body,version,source,updated_at}`; approved synthetic directory only, keyword search, no generated Q&A in R0.

Topic: `{id,title,description,scope,status:'discussing',version,owner_id,participants:string[],created_at,synthetic:true}`. TopicDetail adds `{viewpoints:Viewpoint[],options:Option[],invitations:Invitation[]}`. No formal decision approval API in R0.

Option: `{id,title,description,cost,labor,risks,version,stances:Stance[]}`. Stance: `{member_id,member_name,stance:'support'|'conditional'|'reservation'|'oppose'|'need_info',condition,option_version}`; silence is absence, never support. Conditional stance requires condition text.

Invitation: `{id,topic_id,topic_title,invitee_id,invitee_name,issuer_id,title,description,completion_criteria,resources,compensation,due_date,status:'pending'|'accepted'|'declined'|'negotiating',version,note,created_at,synthetic:true}`. A refusal closes this invitation only. Accepted invitation is not a real project execution authorization. Only issuer/recipient can read its private terms, including within topic detail.

POST/PATCH authenticated mutations require a CSRF token; strict body validation rejects unknown fields. Version conflict is 409; business prerequisite failure 422; inaccessible object uniformly 404. Same idempotency key and same normalized request returns same result, even after network retry; same key with different request rejects 409. Recheck object permission before replaying a cached result. Never derive actor identity from body.

Frontend uses Vite proxy for `/api` during development and same-origin `/api` from the built app. FastAPI serves built `apps/web/dist` in single-server mode. Public terminal has idle logout (5 minutes), no private localStorage, no synthetic AI answers.
