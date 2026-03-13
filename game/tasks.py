from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from .evidence import ENTRY_ACTIVITY_KINDS, run_site_scan
from .models import VerifiedActivity

AUTO_VERIFY_RETRY_DELAYS = (15, 45, 120, 300, 900)


def _set_auto_verify_metadata(
    activity: VerifiedActivity,
    *,
    status: str,
    attempts: int,
    last_error: str = "",
) -> None:
    metadata = dict(activity.metadata or {})
    auto_verify = {
        "status": status,
        "attempts": attempts,
        "last_checked_at": timezone.now().isoformat(),
        "source_url": activity.source_url,
    }
    if last_error:
        auto_verify["last_error"] = last_error[:500]
    metadata["auto_verify"] = auto_verify
    activity.metadata = metadata


def _mark_auto_verify_failed(activity: VerifiedActivity, *, attempts: int, last_error: str = "") -> None:
    _set_auto_verify_metadata(activity, status="failed", attempts=attempts, last_error=last_error)
    activity.status = VerifiedActivity.STATUS_FAILED
    activity.verified_at = None
    activity.save(update_fields=["status", "metadata", "verified_at", "updated_at"])


@shared_task(bind=True, ignore_result=True)
def verify_published_activity(self, activity_id: int) -> dict[str, object]:
    try:
        activity = VerifiedActivity.objects.select_related("identity").get(id=activity_id)
    except VerifiedActivity.DoesNotExist:
        return {"status": "missing"}

    if activity.kind not in ENTRY_ACTIVITY_KINDS:
        return {"status": "ignored"}
    if activity.status == VerifiedActivity.STATUS_VERIFIED:
        return {"status": "already_verified"}
    if activity.status == VerifiedActivity.STATUS_FAILED:
        return {"status": "already_failed"}
    if not activity.source_url:
        return {"status": "missing_source_url"}

    attempts = self.request.retries + 1

    try:
        run_site_scan(activity.identity, manual_page_url=activity.source_url)
    except Exception as exc:
        if self.request.retries >= len(AUTO_VERIFY_RETRY_DELAYS):
            _mark_auto_verify_failed(activity, attempts=attempts, last_error=str(exc))
            return {"status": "failed", "attempts": attempts}
        raise self.retry(exc=exc, countdown=AUTO_VERIFY_RETRY_DELAYS[self.request.retries], max_retries=len(AUTO_VERIFY_RETRY_DELAYS))

    activity.refresh_from_db(fields=["status"])
    if activity.status == VerifiedActivity.STATUS_VERIFIED:
        return {"status": "verified", "attempts": attempts}

    if self.request.retries >= len(AUTO_VERIFY_RETRY_DELAYS):
        _mark_auto_verify_failed(activity, attempts=attempts, last_error="proof_not_found")
        return {"status": "failed", "attempts": attempts}

    _set_auto_verify_metadata(activity, status="pending", attempts=attempts)
    activity.save(update_fields=["metadata", "updated_at"])
    raise self.retry(countdown=AUTO_VERIFY_RETRY_DELAYS[self.request.retries], max_retries=len(AUTO_VERIFY_RETRY_DELAYS))
