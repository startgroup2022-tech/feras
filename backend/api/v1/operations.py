"""Operations endpoints: tasks, weekly reports, campaigns, complaints,
advisors and owner decisions (D02/D03/D04/D07)."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from backend.api.deps import CurrentUser, DbSession
from backend.schemas.domain import (
    AdvisorAssignRequest,
    AdvisorReportSaveRequest,
    AdvisorySessionCreateRequest,
    CampaignCreateRequest,
    CampaignUpdateRequest,
    ComplaintCreateRequest,
    ComplaintDecisionRequest,
    ManagementBriefSaveRequest,
    OwnerDecisionCreateRequest,
    OwnerDecisionUpdateRequest,
    ProjectRecordCreateRequest,
    ProjectRecordUpdateRequest,
    TaskCreateRequest,
    TaskStatusRequest,
    TaskUpdateRequest,
    WeeklyQuestionCreateRequest,
    WeeklyReportCreateRequest,
)
from backend.services import audit_service, operations_service

router = APIRouter(prefix="/operations", tags=["operations"])


# ---- tasks (D03) ----
@router.get("/tasks")
def list_tasks(
    user: CurrentUser, db: DbSession, company_id: int | None = None,
    status_filter: str | None = None, mine: bool = False,
) -> list[dict]:
    return [
        operations_service.serialise_task(t)
        for t in operations_service.list_tasks(
            db, user=user, company_id=company_id, status=status_filter, mine=mine
        )
    ]


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    data["priority"] = payload.priority.value
    task = operations_service.create_task(db, user=user, **data, **ctx)
    return operations_service.serialise_task(task)


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: int, payload: TaskUpdateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("priority") is not None:
        changes["priority"] = changes["priority"].value
    task = operations_service.update_task(
        db, user=user, task_id=task_id, changes=changes, **ctx
    )
    return operations_service.serialise_task(task)


@router.post("/tasks/{task_id}/status")
def change_task_status(
    task_id: int, payload: TaskStatusRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    task = operations_service.change_task_status(
        db, user=user, task_id=task_id, new_status=payload.status.value,
        note=payload.note, **ctx,
    )
    return operations_service.serialise_task(task)


# ---- weekly reports (D02) ----
@router.get("/weekly-reports/questions")
def list_weekly_questions(user: CurrentUser, db: DbSession) -> list[dict]:
    return [
        {"id": q.id, "code": q.code, "text_ar": q.text_ar, "text_en": q.text_en,
         "order_index": q.order_index}
        for q in operations_service.list_weekly_questions(db, user=user)
    ]


@router.post("/weekly-reports/questions", status_code=status.HTTP_201_CREATED)
def create_weekly_question(
    payload: WeeklyQuestionCreateRequest, user: CurrentUser, db: DbSession
) -> dict:
    q = operations_service.create_weekly_question(db, user=user, **payload.model_dump())
    return {"id": q.id, "code": q.code, "text_ar": q.text_ar, "text_en": q.text_en}


@router.get("/weekly-reports")
def list_weekly_reports(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        operations_service.serialise_weekly_report(r)
        for r in operations_service.list_weekly_reports(db, user=user, company_id=company_id)
    ]


@router.post("/weekly-reports", status_code=status.HTTP_201_CREATED)
def submit_weekly_report(
    payload: WeeklyReportCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    answers = data.pop("answers")
    report = operations_service.submit_weekly_report(
        db, user=user, answers=answers, **data, **ctx
    )
    return operations_service.serialise_weekly_report(report)


# ---- campaigns (D02) ----
@router.get("/campaigns")
def list_campaigns(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        operations_service.serialise_campaign(c)
        for c in operations_service.list_campaigns(db, user=user, company_id=company_id)
    ]


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    campaign = operations_service.create_campaign(db, user=user, **payload.model_dump(), **ctx)
    return operations_service.serialise_campaign(campaign)


@router.patch("/campaigns/{campaign_id}")
def update_campaign(
    campaign_id: int, payload: CampaignUpdateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("status") is not None:
        changes["status"] = changes["status"].value
    campaign = operations_service.update_campaign(
        db, user=user, campaign_id=campaign_id, changes=changes, **ctx
    )
    return operations_service.serialise_campaign(campaign)


# ---- complaints (D04, confidential) ----
@router.get("/complaints")
def list_complaints(user: CurrentUser, db: DbSession) -> list[dict]:
    return [
        operations_service.serialise_complaint(c)
        for c in operations_service.list_complaints(db, user=user)
    ]


@router.post("/complaints", status_code=status.HTTP_201_CREATED)
def create_complaint(
    payload: ComplaintCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    complaint = operations_service.create_complaint(
        db, user=user, **payload.model_dump(), **ctx
    )
    return operations_service.serialise_complaint(complaint)


@router.get("/complaints/{complaint_id}")
def get_complaint(complaint_id: int, user: CurrentUser, db: DbSession) -> dict:
    return operations_service.serialise_complaint(
        operations_service.get_complaint(db, user=user, complaint_id=complaint_id)
    )


@router.post("/complaints/{complaint_id}/decision")
def decide_complaint(
    complaint_id: int, payload: ComplaintDecisionRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    complaint = operations_service.decide_complaint(
        db, user=user, complaint_id=complaint_id, new_status=payload.status,
        decision=payload.decision, routed_to_id=payload.routed_to_id, **ctx,
    )
    return operations_service.serialise_complaint(complaint)


# ---- advisors (D04) ----
@router.get("/advisory-sessions")
def list_sessions(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        operations_service.serialise_session(s)
        for s in operations_service.list_sessions(db, user=user, company_id=company_id)
    ]


@router.post("/advisors", status_code=status.HTTP_201_CREATED)
def assign_advisor(
    payload: AdvisorAssignRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    a = operations_service.assign_advisor(db, user=user, **payload.model_dump(), **ctx)
    return {"id": a.id, "company_id": a.company_id, "advisor_user_id": a.advisor_user_id,
            "specialty": a.specialty, "is_active": a.is_active}


@router.get("/advisors")
def list_advisor_assignments(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        operations_service.serialise_assignment(a)
        for a in operations_service.list_advisor_assignments(
            db, user=user, company_id=company_id
        )
    ]


@router.post("/advisory-sessions", status_code=status.HTTP_201_CREATED)
def record_session(
    payload: AdvisorySessionCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    s = operations_service.record_session(db, user=user, **payload.model_dump(), **ctx)
    return operations_service.serialise_session(s)


# ---- advisor monthly reports (S19) ----
@router.get("/advisor-reports")
def list_advisor_reports(
    user: CurrentUser, db: DbSession, company_id: int | None = None,
    period_year: int | None = None, period_month: int | None = None,
) -> list[dict]:
    return [
        operations_service.serialise_advisor_report(r)
        for r in operations_service.list_advisor_reports(
            db, user=user, company_id=company_id,
            period_year=period_year, period_month=period_month,
        )
    ]


@router.post("/advisor-reports", status_code=status.HTTP_201_CREATED)
def save_advisor_report(
    payload: AdvisorReportSaveRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    r = operations_service.save_advisor_report(db, user=user, **payload.model_dump(), **ctx)
    return operations_service.serialise_advisor_report(r)


@router.post("/advisor-reports/{report_id}/submit")
def submit_advisor_report(
    report_id: int, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    r = operations_service.submit_advisor_report(db, user=user, report_id=report_id, **ctx)
    return operations_service.serialise_advisor_report(r)


# ---- owner decisions (D07) ----
@router.get("/owner-decisions")
def list_owner_decisions(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        operations_service.serialise_owner_decision(d)
        for d in operations_service.list_owner_decisions(db, user=user, company_id=company_id)
    ]


@router.post("/owner-decisions", status_code=status.HTTP_201_CREATED)
def create_owner_decision(
    payload: OwnerDecisionCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    d = operations_service.create_owner_decision(db, user=user, **payload.model_dump(), **ctx)
    return operations_service.serialise_owner_decision(d)


@router.patch("/owner-decisions/{decision_id}")
def update_owner_decision(
    decision_id: int, payload: OwnerDecisionUpdateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump(exclude_unset=True)
    status_value = data.get("status")
    if status_value is not None:
        status_value = status_value.value
    d = operations_service.update_owner_decision(
        db, user=user, decision_id=decision_id, new_status=status_value,
        follow_up_note=data.get("follow_up_note"), **ctx,
    )
    return operations_service.serialise_owner_decision(d)


# ---- projects & opportunities (S20) ----
@router.get("/projects")
def list_project_records(
    user: CurrentUser, db: DbSession, company_id: int | None = None,
    record_type: str | None = None, status_filter: str | None = None,
) -> list[dict]:
    return [
        operations_service.serialise_project_record(r)
        for r in operations_service.list_project_records(
            db, user=user, company_id=company_id, record_type=record_type,
            status=status_filter,
        )
    ]


@router.get("/projects/{record_id}")
def get_project_record(record_id: int, user: CurrentUser, db: DbSession) -> dict:
    return operations_service.serialise_project_record(
        operations_service.get_project_record(db, user=user, record_id=record_id)
    )


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project_record(
    payload: ProjectRecordCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    data["record_type"] = payload.record_type.value
    record = operations_service.create_project_record(db, user=user, **data, **ctx)
    return operations_service.serialise_project_record(record)


@router.patch("/projects/{record_id}")
def update_project_record(
    record_id: int, payload: ProjectRecordUpdateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("record_type") is not None:
        changes["record_type"] = changes["record_type"].value
    record = operations_service.update_project_record(
        db, user=user, record_id=record_id, changes=changes, **ctx,
    )
    return operations_service.serialise_project_record(record)


# ---- management reports: the BD five-axis brief (S21) ----
@router.get("/management-briefs")
def list_management_briefs(
    user: CurrentUser, db: DbSession,
    period_year: int | None = None, period_month: int | None = None,
) -> list[dict]:
    return [
        operations_service.serialise_management_brief(b)
        for b in operations_service.list_management_briefs(
            db, user=user, period_year=period_year, period_month=period_month,
        )
    ]


@router.post("/management-briefs", status_code=status.HTTP_201_CREATED)
def save_management_brief(
    payload: ManagementBriefSaveRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    data["urgency"] = payload.urgency.value
    brief = operations_service.save_management_brief(db, user=user, **data, **ctx)
    return operations_service.serialise_management_brief(brief)


@router.post("/management-briefs/{brief_id}/submit")
def submit_management_brief(
    brief_id: int, request: Request, user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    brief = operations_service.submit_management_brief(
        db, user=user, brief_id=brief_id, **ctx,
    )
    return operations_service.serialise_management_brief(brief)
