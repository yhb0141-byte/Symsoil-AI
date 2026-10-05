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
