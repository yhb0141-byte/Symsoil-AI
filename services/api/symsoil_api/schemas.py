import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Login(Body):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    password: str = Field(min_length=1, max_length=128)


class Register(Body):
    token: str = Field(min_length=20, max_length=128)
    password: str = Field(min_length=12, max_length=128)


class AdminInvite(Body):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=80)
    role: Literal["admin", "facilitator", "member"]


class UtteranceCreate(Body):
    text: str = Field(min_length=1, max_length=10000)
    title: str = Field(min_length=1, max_length=160)

    @field_validator("text", "title")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("请输入有效文字")
        return value


class Version(Body):
    object_version: int = Field(ge=1)


class UtterancePatch(UtteranceCreate, Version):
    pass


class Share(Version):
    topic_id: str = Field(min_length=1, max_length=36)
    representation: Literal["original", "candidate"] = "original"
    candidate_id: str | None = Field(default=None, min_length=1, max_length=36)
    candidate_version: int | None = Field(default=None, ge=1)
    choice_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def representation_fields(self):
        if self.representation == "candidate" and (self.candidate_id is None or self.candidate_version is None or self.choice_version is None):
            raise ValueError("分享转述必须指定候选和选择版本")
        if self.representation == "original" and any(value is not None for value in (self.candidate_id, self.candidate_version, self.choice_version)):
            raise ValueError("分享原话不得夹带候选字段")
        return self


class TopicCreate(Body):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=10000)
    scope: str = Field(min_length=1, max_length=5000)


class ParticipantAdd(Version):
    member_id: str = Field(min_length=1, max_length=36)


class OptionCreate(Version):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=10000)
    cost: str = Field(max_length=3000)
    labor: str = Field(max_length=3000)
    risks: str = Field(max_length=3000)


class StanceCreate(Body):
    option_id: str = Field(min_length=1, max_length=36)
    option_version: int = Field(ge=1)
    stance: Literal["support", "conditional", "reservation", "oppose", "need_info"]
    condition: str = Field(default="", max_length=5000, validate_default=True)

    @field_validator("condition")
    @classmethod
    def conditional_requires_text(cls, value, info):
        if info.data.get("stance") == "conditional" and not value.strip():
            raise ValueError("附条件支持需要写明条件")
        return value


class InvitationCreate(Body):
    invitee_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=10000)
    completion_criteria: str = Field(min_length=1, max_length=5000)
    resources: str = Field(max_length=5000)
    compensation: str = Field(max_length=5000)
    due_date: str | None = Field(default=None, max_length=40)

    @field_validator("due_date")
    @classmethod
    def valid_due_date(cls, value):
        if value:
            from datetime import date, datetime
            try:
                date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("截止时间必须为ISO日期或时间") from exc
        return value


class InvitationResponse(Version):
    response: Literal["accepted", "declined", "negotiating"]
    note: str = Field(default="", max_length=5000)


class ApprovalAuthorityCreate(Body):
    member_id: str = Field(min_length=1, max_length=36)
    topic_id: str = Field(min_length=1, max_length=36)
    basis: str = Field(min_length=1, max_length=2000)


class DecisionCreate(Body):
    option_id: str = Field(min_length=1, max_length=36)
    option_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=10000)
    effect_conditions: list[str] = Field(default_factory=list, max_length=20)
    resource_conditions: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("effect_conditions", "resource_conditions")
    @classmethod
    def valid_conditions(cls, values):
        if any(not value.strip() or len(value) > 500 for value in values) or len(values) != len(set(values)):
            raise ValueError("条件不能为空、重复或超过500字")
        return values


class DecisionSubmit(Version):
    rule_version: str = Field(min_length=1, max_length=80)
    required_approver_ids: list[str] = Field(min_length=2, max_length=20)
    required_invitation_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def distinct_required(self):
        if len(set(self.required_approver_ids)) != len(self.required_approver_ids) or len(set(self.required_invitation_ids)) != len(self.required_invitation_ids):
            raise ValueError("必需批准者和任务不得重复")
        return self


class DecisionConditionVerify(Version):
    condition_version: int = Field(ge=1)
    satisfied: bool


class DecisionApprove(Version):
    consent: Literal[True]


class DecisionStart(Version):
    confirm_start: Literal[True]


class ExpressionContext(Body):
    context: str = Field(max_length=3000)
    target_context: str = Field(max_length=1000)
    purpose: str = Field(max_length=1000)


class CandidateCreate(ExpressionContext, Version):
    kind: Literal["everyday", "discussion"]
    text: str = Field(min_length=1, max_length=10000)
    suggestion_token: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value):
        if not value.strip():
            raise ValueError("候选正文不能为空白")
        return value


class CandidatePatch(ExpressionContext, Version):
    candidate_version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=10000)

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value):
        if not value.strip():
            raise ValueError("候选正文不能为空白")
        return value


class ChoiceCreate(Version):
    choice_version: int = Field(ge=0)
    choice: Literal["candidate", "original_only", "no_rephrase"]
    candidate_id: str | None = Field(default=None, min_length=1, max_length=36)
    candidate_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def candidate_fields(self):
        if self.choice == "candidate" and (self.candidate_id is None or self.candidate_version is None):
            raise ValueError("选择候选必须指定候选版本")
        if self.choice != "candidate" and (self.candidate_id is not None or self.candidate_version is not None):
            raise ValueError("原话或拒绝转述选项不得夹带候选字段")
        return self


class UnderstandingCreate(Body):
    utterance_id: str = Field(min_length=1, max_length=36)
    utterance_version: int = Field(ge=1)
    representation: Literal["original", "candidate"]
    candidate_id: str | None = Field(default=None, min_length=1, max_length=36)
    candidate_version: int | None = Field(default=None, ge=1)
    text: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def source_fields(self):
        if not self.text.strip():
            raise ValueError("请填写本人理解")
        if self.representation == "candidate" and (self.candidate_id is None or self.candidate_version is None):
            raise ValueError("转述理解需绑定候选版本")
        if self.representation == "original" and (self.candidate_id is not None or self.candidate_version is not None):
            raise ValueError("原话理解不得夹带候选版本")
        return self


class UnderstandingResponse(Version):
    status: Literal["accurate", "needs_correction", "prefer_in_person"]
    correction: str = Field(max_length=5000)

    @model_validator(mode="after")
    def correction_required(self):
        if self.status == "needs_correction" and not self.correction.strip():
            raise ValueError("需要修正时请写明修正内容")
        return self


class SuggestionRequest(ExpressionContext, Version):
    pass


class SuggestedCandidate(Body):
    kind: Literal["everyday", "discussion"]
    text: str = Field(min_length=1, max_length=10000)

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value):
        if not value.strip():
            raise ValueError("候选正文不能为空白")
        return value


class ModelSuggestions(Body):
    candidates: list[SuggestedCandidate] = Field(max_length=2)
    clarifications: list[str] = Field(max_length=4)

    @model_validator(mode="after")
    def safe_output(self):
        if not self.candidates and not self.clarifications:
            raise ValueError("没有候选或澄清问题")
        kinds = [item.kind for item in self.candidates]
        if len(kinds) != len(set(kinds)):
            raise ValueError("候选类型重复")
        if any(not item.strip() or len(item) > 1000 for item in self.clarifications):
            raise ValueError("澄清问题无效")
        return self


class KnowledgeFields(Body):
    title: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=60)
    body: str = Field(min_length=1, max_length=20000)
    source: str = Field(min_length=1, max_length=1000)
    rights: str = Field(min_length=1, max_length=2000)
    purpose: str = Field(min_length=1, max_length=1000)
    maintainer: str = Field(min_length=1, max_length=500)
    effective_until: str | None = Field(max_length=40)
    requested_scope: Literal["community", "members"]
    requested_member_ids: list[str] = Field(max_length=1000)

    @field_validator("title", "category", "body", "source", "rights", "purpose", "maintainer")
    @classmethod
    def meaningful_fields(cls, value):
        if not value.strip():
            raise ValueError("资料字段不能为空白")
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]", value):
            raise ValueError("资料只接受普通文字，不能包含二进制控制字符")
        return value

    @field_validator("effective_until")
    @classmethod
    def timezone_expiry(cls, value):
        if value is None:
            return value
        from datetime import datetime
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("missing timezone")
        except ValueError as exc:
            raise ValueError("有效期须为带时区的 ISO 时间") from exc
        return value

    @model_validator(mode="after")
    def explicit_audience(self):
        ids = self.requested_member_ids
        if any(not value or len(value) > 36 or re.search(r"[\x00-\x1f\x7f\ud800-\udfff]", value) for value in ids) or len(set(ids)) != len(ids):
            raise ValueError("成员名单必须为不同的明确 ID")
        if self.requested_scope == "community" and ids:
            raise ValueError("全体成员范围不能夹带指定名单")
        if self.requested_scope == "members" and not ids:
            raise ValueError("申请固定名单至少需要一位成员")
        return self


class KnowledgePatch(KnowledgeFields, Version):
    pass


class KnowledgeSubmit(Version):
    revision_id: str = Field(min_length=1, max_length=36)
    reviewer_id: str = Field(min_length=1, max_length=36)
    consent: Literal[True]

    @field_validator("revision_id", "reviewer_id")
    @classmethod
    def safe_submission_ids(cls, value):
        if re.search(r"[\x00-\x1f\x7f\ud800-\udfff]", value):
            raise ValueError("审核标识必须为有效文字")
        return value

    @field_validator("consent", mode="before")
    @classmethod
    def explicit_boolean_consent(cls, value):
        if value is not True:
            raise ValueError("送审必须由本人明确授权")
        return value


class KnowledgeReviewRequest(Version):
    revision_id: str = Field(min_length=1, max_length=36)
    decision: Literal["approve", "changes_requested"]
    reason: str = Field(max_length=2000)

    @field_validator("reason", "revision_id")
    @classmethod
    def safe_review_text(cls, value):
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]", value):
            raise ValueError("审核字段只接受普通文字")
        return value

    @model_validator(mode="after")
    def return_reason(self):
        if self.decision == "changes_requested" and not self.reason.strip():
            raise ValueError("退回修改须写明理由")
        return self


class KnowledgeRestrict(Version):
    scope: Literal["members"]
    member_ids: list[str] = Field(max_length=1000)

    @field_validator("member_ids")
    @classmethod
    def explicit_ids(cls, value):
        if len(set(value)) != len(value) or any(not item or len(item) > 36 or re.search(r"[\x00-\x1f\x7f\ud800-\udfff]", item) for item in value):
            raise ValueError("受众须为不同的明确成员 ID")
        return value


class KnowledgeAnswerRequest(Body):
    question: str = Field(min_length=1, max_length=200)
    use_model: bool = False

    @field_validator("question")
    @classmethod
    def meaningful_question(cls, value):
        if not value.strip():
            raise ValueError("请输入问题")
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]", value):
            raise ValueError("问题只接受普通文字")
        return value


class ModelKnowledgeAnswer(Body):
    answer: str = Field(max_length=10000)
    citation_ids: list[str] = Field(max_length=6)

    @field_validator("answer")
    @classmethod
    def safe_answer_text(cls, value):
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]", value):
            raise ValueError("模型回答不是普通文字")
        return value

    @model_validator(mode="after")
    def valid_citation_ids(self):
        if any(not item or len(item) > 160 for item in self.citation_ids) or len(set(self.citation_ids)) != len(self.citation_ids):
            raise ValueError("引用标识无效或重复")
        if self.answer.strip() and not self.citation_ids:
            raise ValueError("非空回答必须引用本次资料")
        return self


class CorrectionText(Body):
    text: str = Field(min_length=1, max_length=2000)
    consent: Literal[True]

    @field_validator("text")
    @classmethod
    def safe_text(cls, value):
        if not value.strip() or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]", value):
            raise ValueError("请填写普通非空文字")
        return value

    @field_validator("consent", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError("请本人明确确认分享范围")
        return value


class CorrectionCreate(CorrectionText):
    document_id: str = Field(min_length=1, max_length=36)
    revision_id: str = Field(min_length=1, max_length=36)
    access_epoch: int = Field(ge=1)
    expected_recipient_id: str = Field(min_length=1, max_length=36)

    @field_validator("document_id", "revision_id", "expected_recipient_id")
    @classmethod
    def safe_ids(cls, value):
        if re.search(r"[\x00-\x1f\x7f\ud800-\udfff]", value):
            raise ValueError("标识必须为有效文字")
        return value


class CorrectionRespond(CorrectionText, Version):
    pass
