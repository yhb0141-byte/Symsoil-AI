export type Role = 'admin' | 'facilitator' | 'member'
export interface User { id: string; username: string; display_name: string; role: Role; active: boolean }
export interface Member { id: string; display_name: string }
export interface Session { user: User; csrf_token: string }
export interface Document { id: string; title: string; category: string; body: string; version: number; source: string; updated_at: string }
export interface Utterance { id: string; title: string; text: string; version: number; confirmed_version: number | null; confirmed_at: string | null; shared_topic_id: string | null; created_at: string; updated_at: string }
export type StanceKind = 'support' | 'conditional' | 'reservation' | 'oppose' | 'need_info'
export interface Stance { member_id: string; member_name: string; stance: StanceKind; condition: string; option_version: number }
export interface Option { id: string; title: string; description: string; cost: string; labor: string; risks: string; version: number; stances: Stance[] }
export interface Viewpoint { id: string; author_id: string; author_name: string; text: string; utterance_version: number; confirmed_at: string; representation: 'original' | 'candidate'; candidate_id: string | null; candidate_version: number | null }
export interface Topic { id: string; title: string; description: string; scope: string; status: 'discussing'; version: number; owner_id: string; participants: string[]; created_at: string; synthetic: true }
export interface TopicDetail extends Topic { viewpoints: Viewpoint[]; options: Option[]; invitations: Invitation[] }
export type InvitationResponse = 'accepted' | 'declined' | 'negotiating'
export interface Invitation { id: string; topic_id: string; topic_title: string; invitee_id: string; invitee_name: string; issuer_id: string; title: string; description: string; completion_criteria: string; resources: string; compensation: string; due_date: string | null; status: 'pending' | InvitationResponse; version: number; note: string; created_at: string; synthetic: true }
export interface Dashboard { counts: { topics: number; open_invitations: number; utterances: number; documents: number }; pending: Invitation[]; topics: Topic[]; ai: { available: false }; release: { stage: 'R0'; synthetic: true } }
export interface AuditEvent { id?: string; action: string; object_id?: string; object_type?: string; created_at?: string; timestamp?: string; detail?: string }
export interface SessionStatus { id?: string; created_at?: string; expires_at?: string; current?: boolean; revoked?: boolean; last_seen_at?: string; [key: string]: unknown }

export type CandidateKind = 'everyday' | 'discussion'
export interface Candidate { id: string; utterance_id: string; utterance_version: number; kind: CandidateKind; text: string; context: string; target_context: string; purpose: string; version: number; origin: 'manual' | 'local_model'; confirmed_version: number | null; confirmed_at: string | null; created_at: string; updated_at: string }
export type RephraseChoice = 'candidate' | 'original_only' | 'no_rephrase'
export interface Choice { utterance_id: string; utterance_version: number; version: number; choice: RephraseChoice; candidate_id: string | null; candidate_version: number | null; confirmed_at: string | null; updated_at: string }
export interface ExpressionDetail { utterance: Utterance; candidates: Candidate[]; choice: Choice | null; share: { representation: 'original' | 'candidate'; candidate_id: string | null; candidate_version: number | null } | null }
export type UnderstandingStatus = 'pending' | 'accurate' | 'needs_correction' | 'prefer_in_person'
export interface Understanding { id: string; topic_id: string; utterance_id: string; utterance_version: number; representation: 'original' | 'candidate'; candidate_id: string | null; candidate_version: number | null; requester_id: string; requester_name: string; author_id: string; author_name: string; text: string; status: UnderstandingStatus; correction: string; version: number; created_at: string; updated_at: string }
export interface AiStatus { enabled: boolean; available: boolean; provider: 'ollama' | null; model: string | null; reason: string }
export interface ModelSuggestions { utterance_version: number; candidates: { kind: CandidateKind; text: string; suggestion_token: string }[]; clarifications: string[]; provider: 'ollama'; model: string }
