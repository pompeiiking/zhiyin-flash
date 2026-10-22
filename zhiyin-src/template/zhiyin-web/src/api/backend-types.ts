// Generated from ../contracts/openapi.json. Run npm run sync:backend. Do not hand edit.

export type NoteView = {
  "created_at": string
  "done"?: boolean
  "id": string
  "kind": string
  "text": string
}

export type NoteCreateRequest = {
  "kind"?: string
  "text": string
}

export type NoteDoneRequest = {
  "done": boolean
}

export type AcademicPanelView = {
  "courses"?: Array<AcademicCourseView>
  "grades"?: Array<AcademicGradeView>
  "imported_at"?: string
  "note"?: string
  "school"?: string
  "source"?: string
  "term"?: string
}

export type AcademicImportRequest = {
  "courses"?: string
  "grades"?: string
  "school"?: string
  "term"?: string
}

export type AcademicImportAck = {
  "courses"?: number
  "courses_scheduled"?: number
  "grades"?: number
  "imported_at"?: string
  "notes"?: Array<string>
  "school"?: string
  "source"?: string
  "term"?: string
  "wrote_profile"?: Array<string>
}

export type ConversationMaterialView = {
  "chars"?: number
  "material_id": string
  "name"?: string
  "size"?: number
}

export type TaskSessionView = {
  "last_active_at"?: (string | null)
  "last_message"?: (string | null)
  "last_message_at"?: (string | null)
  "lead_agent_name"?: string
  "message_count"?: number
  "progress"?: number
  "stage": LoopStage
  "stage_label": string
  "status"?: TaskStatus
  "task_id": string
  "task_name": string
}

export type SessionListView = {
  "current_task_id"?: (string | null)
  "sessions"?: Array<TaskSessionView>
}

export type MessageRequest = {
  "client_msg_id"?: (string | null)
  "material_ids"?: Array<string>
  "message": string
  "option_id"?: (string | null)
  "option_value"?: unknown
  "task_id": string
}

export type GuideOptionView = {
  "label": string
  "option_id": string
  "value"?: unknown
}

export type ConversationTurnView = {
  "badge": AgentBadgeView
  "changed_assets"?: Array<AssetVersionView>
  "disclosure"?: (DisclosureView | null)
  "guide": BehaviorGuideView
  "messages"?: Array<ConversationMessageView>
  "pipeline_cards"?: Array<PipelineCardView>
  "stage": LoopStage
  "task_id": string
}

export type ProfileFieldView = {
  "attributes"?: Record<string, unknown>
  "confidence"?: number
  "entry_type"?: ProfileEntryType
  "entry_type_label"?: string
  "entry_version"?: number
  "event_at"?: (string | null)
  "evidence"?: Array<string>
  "key": string
  "label"?: string
  "origin_ref"?: string
  "source": ProfileSource
  "status"?: ProfileEntryStatus
  "superseded_by"?: string
  "updated_at": string
  "valid_from"?: (string | null)
  "valid_to"?: (string | null)
  "value"?: unknown
  "verification"?: ProfileVerification
  "verification_label"?: string
}

export type IntelListView = {
  "basis"?: string
  "basis_kind"?: string
  "counts"?: Record<string, number>
  "fetched_at"?: string
  "items"?: Array<IntelItemView>
  "major"?: string
  "message"?: string
  "occupation_sources"?: Record<string, number>
  "query"?: Record<string, Array<string>>
  "status"?: string
}

export type IntelItemView = {
  "fetched_at"?: string
  "id": string
  "kind"?: string
  "kind_label"?: string
  "relation"?: string
  "source_name"?: string
  "source_url"?: string
  "text"?: string
  "title"?: string
}

export type CalendarNodeView = {
  "due_at"?: (string | null)
  "node_id": string
  "related_task_text"?: string
  "source"?: "planner" | "coach" | "manual"
  "title": string
}

export type AchievementListView = {
  "items"?: Array<AchievementView>
  "total"?: number
  "unlocked"?: number
}

export type ActionPlanView = {
  "exported_at"?: (string | null)
  "has_plan"?: boolean
  "id"?: string
  "next_task"?: (ActionTaskView | null)
  "phases"?: Array<ActionPhaseView>
  "plan_id"?: (string | null)
  "reminders_synced"?: boolean
}

export type ActionTaskDoneRequest = {
  "done"?: boolean
  "task_id": string
}

export type DirectionPlanListView = {
  "match_score_method"?: string
  "plans"?: Array<DirectionPlanView>
  "selected_id"?: (string | null)
}

export type ReportFullTextView = {
  "generated_at": string
  "methodologies"?: Array<string>
  "report_id": string
  "sections"?: Array<ReportSectionView>
  "sources"?: Array<string>
  "swot"?: Record<string, unknown>
  "toc"?: Array<ReportTocItemView>
  "verdict"?: Record<string, unknown>
  "version": number
}

export type AssetVersionView = {
  "asset_id": string
  "asset_type": AssetType
  "created_at": string
  "depends_on_profile_keys"?: Array<string>
  "diff_from_previous"?: (string | null)
  "needs_recompute"?: boolean
  "recompute_reason"?: string
  "version": number
}

export type TrackEventView = {
  "detail"?: string
  "due_at"?: (string | null)
  "id": string
  "occurred_at"?: (string | null)
  "related_stage"?: (string | null)
  "related_task_id"?: (string | null)
  "title": string
  "type": "milestone_done" | "reminder" | "warning" | "semester_review" | "coach_message"
}

export type BootstrapView = {
  "app_name"?: string
  "banners"?: Array<BannerView>
  "copy_bundle"?: Record<string, string>
  "faqs"?: Array<FaqView>
  "feature_flags"?: Record<string, boolean>
  "identity"?: Record<string, string>
  "menus"?: Array<MenuView>
  "routes"?: Array<RouteView>
  "task_entries"?: Array<TaskEntryView>
  "trust_blocks"?: Array<TrustBlockView>
}

export type TheoryCardView = {
  "id": string
  "name": string
  "product_usage"?: string
  "school"?: string
  "summary"?: string
}

export type TaskEdit = {
  "client_request_id"?: (string | null)
  "due_date"?: (string | null)
  "estimated_minutes"?: (number | null)
  "expected_task"?: (TaskValues | null)
  "parent_task_id"?: (string | null)
  "phase_id": string
  "progress"?: number
  "scheduled_at"?: (string | null)
  "status"?: "pending" | "in_progress" | "waiting" | "completed"
  "text": string
  "waiting_reason"?: string
}

export type PhaseEdit = {
  "blocking_conditions"?: Array<string>
  "client_request_id"?: (string | null)
  "depends_on"?: Array<string>
  "ends_at"?: (string | null)
  "expected_phase"?: (PhaseValues | null)
  "handoff_requirements"?: Array<string>
  "name": string
  "starts_at"?: (string | null)
}

export type Preferences = {
  "academic_analysis"?: boolean
  "automatic_memory"?: boolean
  "material_analysis"?: boolean
  "proactive_reminders"?: boolean
  "quiet_end"?: (string | null)
  "quiet_start"?: (string | null)
  "timezone"?: string
}

export type Semester = {
  "first_monday": string
  "periods": Array<Period>
  "timezone"?: string
  "weekly_available_minutes"?: (number | null)
  "weeks"?: number
}

export type ReviewEdit = {
  "adjustment"?: (TaskEdit | null)
  "client_request_id"?: (string | null)
  "expected_task"?: (TaskValues | null)
  "expected_updated_at"?: (string | null)
  "note"?: string
  "reason": string
  "result"?: "continue" | "adjust" | "complete"
  "task_id": string
}

export type NotificationEdit = {
  "snoozed_until"?: (string | null)
  "status": "pending" | "read" | "later" | "done"
}

export type MeasurementEdit = {
  "asset_type": "report" | "direction_plan"
  "expected": Array<Measurement>
  "measurements": Array<Measurement>
  "subject_id": string
  "version": number
}

export type MeasurementRecordView = {
  "asset_type": "report" | "direction_plan"
  "measurements": Array<Measurement>
  "recorded_at": string
  "subject_id": string
  "version": number
}

export type DirectionWeights = {
  "jobs"?: number
  "location"?: number
  "major"?: number
  "salary"?: number
  "stability"?: number
}

export type PreferencesEdit = {
  "academic_analysis"?: boolean
  "automatic_memory"?: boolean
  "expected": Preferences
  "material_analysis"?: boolean
  "proactive_reminders"?: boolean
  "quiet_end"?: (string | null)
  "quiet_start"?: (string | null)
  "timezone"?: string
}

export type SemesterEdit = {
  "expected": (Semester | null)
  "first_monday": string
  "periods": Array<Period>
  "timezone"?: string
  "weekly_available_minutes"?: (number | null)
  "weeks"?: number
}

export type DirectionWeightsEdit = {
  "expected": DirectionWeights
  "jobs"?: number
  "location"?: number
  "major"?: number
  "salary"?: number
  "stability"?: number
}

export type AcademicPreview = {
  "courses"?: Array<CourseEntry>
  "expected_version": string
  "expires_at": string
  "grades"?: Array<GradeEntry>
  "kind": "courses" | "grades"
  "preview_id": string
  "replace_count": number
  "school": string
  "term": string
  "warnings"?: Array<string>
}

export type AcademicPreviewRequest = {
  "kind": "courses" | "grades"
  "material_id"?: string
  "school"?: string
  "term"?: string
  "text"?: string
}

export type WorkspacePageView = {
  "academic_panel"?: (AcademicPanelView | null)
  "action_panel"?: (StagePanelView | null)
  "axis_a_stage"?: (string | null)
  "coach_messages"?: Array<Record<string, unknown>>
  "collection_panel"?: CollectionPanelView
  "dependencies"?: Array<DependencyEdgeView>
  "layout_panel"?: Array<LayoutBlockView>
  "plan_panel"?: (StagePanelView | null)
  "profile_panel"?: ProfilePanelView
  "report_panel"?: (StagePanelView | null)
  "review_panel"?: (StagePanelView | null)
}

export type ExportResultView = {
  "available"?: boolean
  "message"?: string
  "object_key"?: (string | null)
}

export type LoginResult = {
  "role": string
  "token": string
  "user_id": string
}

export type AuthRequest = {
  "account": string
  "password": string
}

export type CoachNotificationView = {
  "action"?: (Record<string, unknown> | null)
  "body"?: string
  "channel"?: string
  "id": string
  "occurred_at"?: (string | null)
  "related_task_id"?: (string | null)
  "title": string
}

export type PortalView = {
  "app_name"?: string
  "banners"?: Array<BannerView>
  "copy_bundle"?: Record<string, string>
  "faqs"?: Array<FaqView>
  "feature_flags"?: Record<string, boolean>
  "task_entries"?: Array<TaskEntryView>
  "trust_blocks"?: Array<TrustBlockView>
}

export type CapabilityListView = {
  "generated_at"?: string
  "items"?: Array<CapabilityItemView>
}

export type SessionRenameRequest = {
  "task_name": string
}

export type AcademicCourseView = {
  "category"?: string
  "credit"?: string
  "end_period"?: number
  "name": string
  "place"?: string
  "start_period"?: number
  "teacher"?: string
  "weekday"?: number
  "weeks"?: string
}

export type AcademicGradeView = {
  "category"?: string
  "credit"?: string
  "kind"?: string
  "name": string
  "point"?: string
  "score"?: string
  "term"?: string
}

export type LoopStage = "collect" | "diagnose" | "decide" | "act" | "review"

export type TaskStatus = "active" | "paused" | "completed"

export type AgentBadgeView = {
  "agent_id": string
  "name": string
  "role_summary"?: string
  "theory_refs"?: Array<TheoryRefView>
}

export type DisclosureView = {
  "from_agent"?: (string | null)
  "kind": "lead_change" | "theory_change" | "conclusion_change"
  "text": string
  "theory_refs"?: Array<TheoryRefView>
  "to_agent"?: (string | null)
}

export type BehaviorGuideView = {
  "kind": "question" | "options" | "task" | "reminder"
  "options"?: Array<GuideOptionView>
  "question"?: (string | null)
  "reminder"?: (GuideReminderView | null)
  "task"?: (GuideTaskView | null)
  "text"?: string
}

export type ConversationMessageView = {
  "agent_id"?: (string | null)
  "agent_name"?: (string | null)
  "clues"?: Array<string>
  "created_at"?: (string | null)
  "intel_refs"?: Array<IntelRefView>
  "renderables"?: Array<RenderableView>
  "role": "agent" | "user" | "system"
  "text": string
  "theory_refs"?: Array<TheoryRefView>
}

export type PipelineCardView = {
  "active"?: boolean
  "current_output"?: (Record<string, unknown> | null)
  "evaluation"?: (Record<string, unknown> | null)
  "stage": LoopStage
  "status"?: "empty" | "in_progress" | "done"
  "theory_models"?: Array<TheoryRefView>
  "title": string
}

export type ProfileEntryType = "learning_background" | "interest" | "experience" | "ability" | "career_focus" | "values" | "condition" | "supplement"

export type ProfileSource = "resume" | "conversation" | "assessment" | "behavior_inference" | "mentor" | "record" | "user_edit"

export type ProfileEntryStatus = "active" | "corrected" | "conflict" | "expired" | "withdrawn" | "superseded"

export type ProfileVerification = "self_reported" | "user_confirmed" | "record" | "verified" | "pending"

export type AchievementView = {
  "key": string
  "unlocked"?: boolean
  "unlocked_at"?: (string | null)
}

export type ActionTaskView = {
  "done"?: boolean
  "done_at"?: (string | null)
  "due_date"?: (string | null)
  "estimated_minutes"?: (number | null)
  "parent_task_id"?: (string | null)
  "phase"?: string
  "progress"?: number
  "scheduled_at"?: (string | null)
  "status"?: "pending" | "in_progress" | "waiting" | "completed"
  "task_id": string
  "text": string
  "waiting_reason"?: string
}

export type ActionPhaseView = {
  "blocked_by"?: Array<string>
  "blocking_conditions"?: Array<string>
  "date_range"?: string
  "depends_on"?: Array<string>
  "ends_at"?: (string | null)
  "handoff_requirements"?: Array<string>
  "id"?: string
  "name": string
  "starts_at"?: (string | null)
  "tag"?: string
  "tasks"?: Array<ActionTaskView>
}

export type DirectionPlanView = {
  "fit_reason"?: string
  "gaps"?: Array<PlanGapView>
  "id": string
  "main_risk"?: string
  "match_score"?: (number | null)
  "name": string
  "revocable"?: boolean
  "role": PlanRole
  "selected"?: boolean
  "selected_at"?: (string | null)
  "target_desc"?: string
}

export type ReportSectionView = {
  "id": string
  "items"?: Array<ReportDimensionItemView>
  "method"?: string
  "title": string
}

export type ReportTocItemView = {
  "id": string
  "title": string
}

export type AssetType = "report" | "direction_plan" | "action_plan"

export type BannerView = {
  "action_label"?: string
  "action_route"?: string
  "body"?: string
  "code": string
  "title": string
}

export type FaqView = {
  "answer": string
  "code": string
  "question": string
}

export type MenuView = {
  "key": string
  "label": string
  "route": string
  "sort_order"?: number
  "visible"?: boolean
}

export type RouteView = {
  "page_code": string
  "path": string
  "require_login"?: boolean
  "sort_order"?: number
}

export type TaskEntryView = {
  "code": string
  "label": string
  "lead_agent_name"?: (string | null)
  "sort_order"?: number
  "target_stage"?: (LoopStage | null)
}

export type TrustBlockView = {
  "body"?: string
  "code": string
  "expandable_ref"?: string
  "title": string
}

export type TaskValues = {
  "due_date"?: (string | null)
  "estimated_minutes"?: (number | null)
  "parent_task_id"?: (string | null)
  "phase_id": string
  "progress"?: number
  "scheduled_at"?: (string | null)
  "status"?: "pending" | "in_progress" | "waiting" | "completed"
  "text": string
  "waiting_reason"?: string
}

export type PhaseValues = {
  "blocking_conditions"?: Array<string>
  "depends_on"?: Array<string>
  "ends_at"?: (string | null)
  "handoff_requirements"?: Array<string>
  "name": string
  "starts_at"?: (string | null)
}

export type Period = {
  "end": string
  "number": number
  "start": string
}

export type Measurement = {
  "key": string
  "label": string
  "maximum"?: number
  "measured_at": string
  "method": string
  "minimum"?: number
  "origin"?: "self_report" | "assessment" | "external"
  "source": string
  "threshold"?: (number | null)
  "value": number
}

export type CourseEntry = {
  "category"?: string
  "credit"?: string
  "end_period"?: number
  "name": string
  "place"?: string
  "start_period"?: number
  "teacher"?: string
  "weekday"?: number
  "weeks"?: string
}

export type GradeEntry = {
  "category"?: string
  "credit"?: string
  "kind"?: string
  "name": string
  "point"?: string
  "score"?: string
  "term"?: string
}

export type StagePanelView = {
  "diff"?: (string | null)
  "evaluation"?: string
  "stage": LoopStage
  "theory_models"?: Array<TheoryRefView>
  "title": string
  "updated_at"?: (string | null)
  "version"?: (number | null)
}

export type CollectionPanelView = {
  "blocked"?: Array<string>
  "by_source"?: Record<string, number>
  "items"?: Array<CollectionItemView>
  "missing"?: number
  "next_source"?: (string | null)
  "unverified"?: number
}

export type DependencyEdgeView = {
  "from_asset": string
  "to_asset": string
  "via_profile_keys"?: Array<string>
}

export type LayoutBlockView = {
  "hint"?: string
  "id": string
  "label"?: string
  "priority"?: number
  "weight"?: number
  "why"?: string
}

export type ProfilePanelView = {
  "clues"?: Array<ProfileClueView>
  "conflicts"?: Array<ProfileConflictView>
  "coverage"?: number
  "fields"?: Array<ProfileFieldView>
  "gaps"?: Array<ProfileGapView>
  "overall_confidence"?: number
  "updated_at"?: (string | null)
}

export type CapabilityItemView = {
  "available"?: boolean
  "fallback"?: string
  "key": string
  "label": string
  "reason"?: string
}

export type TheoryRefView = {
  "name": string
  "stage"?: string
  "theory_id": string
}

export type GuideReminderView = {
  "detail"?: string
  "due_at"?: (string | null)
  "title": string
}

export type GuideTaskView = {
  "due_date"?: (string | null)
  "task_id": string
  "text": string
}

export type IntelRefView = {
  "id": string
  "kind_label"?: string
  "source_name"?: string
  "source_url"?: string
  "title"?: string
}

export type RenderableView = {
  "kind": string
  "payload"?: Record<string, unknown>
  "source_refs"?: Array<IntelRefView>
  "title"?: string
}

export type PlanGapView = {
  "current_state"?: string
  "requirement": string
  "suggestion"?: string
}

export type PlanRole = "main" | "parallel" | "fallback"

export type ReportDimensionItemView = {
  "conclusion": string
  "evidence": string
  "index": number
  "name": string
  "tag": string
}

export type CollectionItemView = {
  "ask"?: string
  "available"?: boolean
  "confirmable"?: boolean
  "field_source"?: string
  "got"?: boolean
  "key": string
  "label": string
  "source": string
  "state"?: string
  "status_text"?: string
  "value"?: unknown
  "verification"?: string
  "why": string
}

export type ProfileClueView = {
  "created_at": string
  "evidence"?: Array<string>
  "field_keys"?: Array<string>
  "id": string
  "invalidated_reason"?: string
  "status"?: ProfileClueStatus
  "text": string
  "updated_at": string
}

export type ProfileConflictView = {
  "attributes"?: Record<string, unknown>
  "change_reason"?: string
  "created_at": string
  "evidence"?: Array<string>
  "id": string
  "key": string
  "label"?: string
  "origin_ref"?: string
  "replaced_at"?: (string | null)
  "source": ProfileSource
  "status"?: ProfileEntryStatus
  "status_label"?: string
  "value"?: unknown
  "verification"?: ProfileVerification
  "verification_label"?: string
}

export type ProfileGapView = {
  "key": string
  "label"?: string
  "reason": string
  "suggested_next_action"?: string
}

export type ProfileClueStatus = "proposed" | "invalid" | "confirmed"

export type CapabilitiesView = CapabilityListView

