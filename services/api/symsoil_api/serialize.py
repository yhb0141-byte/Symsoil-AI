from sqlalchemy import select

from .models import ExpressionCandidate, ExpressionChoice, ExpressionShare, Invitation, Option, Participant, Stance, Topic, User, Utterance


def user_data(user):
    return {key: getattr(user, key) for key in ("id", "username", "display_name", "role", "active")}


def utterance_data(item):
    return {key: getattr(item, key) for key in ("id", "title", "text", "version", "confirmed_version", "confirmed_at", "shared_topic_id", "created_at", "updated_at")}


def document_data(item):
    return {key: getattr(item, key) for key in ("id", "title", "category", "body", "version", "source", "updated_at")}


def topic_data(db, topic):
    data = {key: getattr(topic, key) for key in ("id", "title", "description", "scope", "status", "version", "owner_id", "created_at")}
    data["participants"] = list(db.scalars(select(Participant.user_id).where(Participant.topic_id == topic.id).order_by(Participant.user_id)))
    data["synthetic"] = True
    return data


def viewpoint_data(db, item):
    return current_viewpoint(db, item)


def current_viewpoint(db, item):
    if not item or not item.shared_topic_id or item.shared_version != item.version or item.confirmed_version != item.version:
        return None
    metadata = db.get(ExpressionShare, item.id)
    representation = metadata.representation if metadata else "original"
    candidate_id = candidate_version = None
    confirmed_at = item.confirmed_at
    if metadata and metadata.utterance_version != item.version:
        return None
    if representation == "candidate":
        candidate = db.get(ExpressionCandidate, metadata.candidate_id)
        choice = db.get(ExpressionChoice, item.id)
        if not candidate or not choice or candidate.utterance_id != item.id or candidate.utterance_version != item.version or candidate.version != metadata.candidate_version or candidate.confirmed_version != candidate.version:
            return None
        if choice.utterance_version != item.version or choice.choice != "candidate" or choice.candidate_id != candidate.id or choice.candidate_version != candidate.version:
            return None
        if item.shared_text != candidate.text:
            return None
        candidate_id, candidate_version, confirmed_at = candidate.id, candidate.version, candidate.confirmed_at
    elif representation != "original" or item.shared_text != item.text:
        return None
    author = db.get(User, item.author_id)
    return {"id": item.id, "author_id": item.author_id, "author_name": author.display_name, "text": item.shared_text, "utterance_version": item.shared_version, "confirmed_at": confirmed_at, "representation": representation, "candidate_id": candidate_id, "candidate_version": candidate_version}


def candidate_data(item):
    return {key: getattr(item, key) for key in ("id", "utterance_id", "utterance_version", "kind", "text", "context", "target_context", "purpose", "version", "origin", "confirmed_version", "confirmed_at", "created_at", "updated_at")}


def choice_data(item):
    return {key: getattr(item, key) for key in ("utterance_id", "utterance_version", "version", "choice", "candidate_id", "candidate_version", "confirmed_at", "updated_at")}


def expression_detail(db, item):
    candidates = db.scalars(select(ExpressionCandidate).where(ExpressionCandidate.utterance_id == item.id, ExpressionCandidate.utterance_version == item.version).order_by(ExpressionCandidate.kind))
    choice = db.get(ExpressionChoice, item.id)
    current = current_viewpoint(db, item)
    return {"utterance": utterance_data(item), "candidates": [candidate_data(candidate) for candidate in candidates], "choice": choice_data(choice) if choice and choice.utterance_version == item.version else None, "share": {key: current[key] for key in ("representation", "candidate_id", "candidate_version")} if current else None}


def understanding_data(db, item):
    data = {key: getattr(item, key) for key in ("id", "topic_id", "utterance_id", "utterance_version", "representation", "candidate_id", "candidate_version", "requester_id", "author_id", "text", "status", "correction", "version", "created_at", "updated_at")}
    data["requester_name"] = db.get(User, item.requester_id).display_name
    data["author_name"] = db.get(User, item.author_id).display_name
    return data


def understanding_source_current(db, item):
    source = db.get(Utterance, item.utterance_id)
    current = current_viewpoint(db, source)
    if not current or source.shared_topic_id != item.topic_id:
        return False
    if not db.get(Participant, (item.topic_id, item.requester_id)):
        return False
    return all(current[key] == getattr(item, key) for key in ("utterance_version", "representation", "candidate_id", "candidate_version"))


def invitation_data(db, item):
    data = {key: getattr(item, key) for key in ("id", "topic_id", "invitee_id", "issuer_id", "title", "description", "completion_criteria", "resources", "compensation", "due_date", "status", "version", "note", "created_at")}
    data.update(topic_title=db.get(Topic, item.topic_id).title, invitee_name=db.get(User, item.invitee_id).display_name, synthetic=True)
    return data


def topic_detail(db, topic, actor_id):
    data = topic_data(db, topic)
    data["viewpoints"] = [view for item in db.scalars(select(Utterance).where(Utterance.shared_topic_id == topic.id).order_by(Utterance.created_at)) if (view := current_viewpoint(db, item)) is not None]
    options = []
    for item in db.scalars(select(Option).where(Option.topic_id == topic.id).order_by(Option.id)):
        option = {key: getattr(item, key) for key in ("id", "title", "description", "cost", "labor", "risks", "version")}
        option["stances"] = [{"member_id": stance.member_id, "member_name": db.get(User, stance.member_id).display_name, "stance": stance.stance, "condition": stance.condition, "option_version": stance.option_version} for stance in db.scalars(select(Stance).where(Stance.option_id == item.id).order_by(Stance.member_id))]
        options.append(option)
    data["options"] = options
    data["invitations"] = [invitation_data(db, item) for item in db.scalars(select(Invitation).where(Invitation.topic_id == topic.id, (Invitation.issuer_id == actor_id) | (Invitation.invitee_id == actor_id)).order_by(Invitation.created_at))]
    return data
