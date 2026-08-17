"""Shared quota reservation policy for user image requests."""

from services.auth_service import auth_service

def reserve_user_image_quota(user_id: str, count: int) -> str:
    # Unknown and unlimited account quotas cannot produce a safe finite cap.
    # The account selector remains authoritative for those pools.
    from services.account_service import account_service
    from services.config import config

    stats = account_service.get_stats()
    global_limit = None
    if not int(stats.get("unknown_quota_count") or 0) and not int(stats.get("unlimited_quota_count") or 0):
        global_limit = max(0, int(stats.get("total_quota") or 0))
    return auth_service.reserve_successful_images(
        user_id,
        count,
        max(0, int(config.user_daily_image_limit or 0)),
        global_limit=global_limit,
    )
