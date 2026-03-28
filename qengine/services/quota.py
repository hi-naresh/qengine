import qengine.helpers as jh


def check_quota(user_id: str, feature: str) -> tuple:
    """
    Check if a user has remaining quota for a feature.
    Returns (allowed: bool, message: str).
    Admin users always allowed.
    """
    from qengine.models.User import get_user_by_id
    from qengine.models.UserQuota import get_quota

    user = get_user_by_id(user_id)
    if not user:
        return False, 'User not found'

    if user.role == 'admin':
        return True, ''

    quota = get_quota(user_id, feature)
    if not quota:
        return False, f'No quota configured for {feature}'

    if quota.max_runs == -1:
        return True, ''  # unlimited

    # Check period reset for periodic quotas
    now = jh.now_to_timestamp(True)
    if quota.period in ('weekly', 'monthly', 'daily') and quota.period_reset_at and now >= quota.period_reset_at:
        # Reset the counter
        if quota.period == 'weekly':
            new_reset = now + (7 * 24 * 60 * 60 * 1000)
        elif quota.period == 'monthly':
            new_reset = now + (30 * 24 * 60 * 60 * 1000)
        else:  # daily
            new_reset = now + (24 * 60 * 60 * 1000)

        from qengine.models.UserQuota import update_quota
        update_quota(user_id, feature, used_runs=0, period_reset_at=new_reset)
        return True, ''

    if quota.used_runs >= quota.max_runs:
        return False, f'Quota exceeded: {quota.used_runs}/{quota.max_runs} {feature} runs used this {quota.period} period'

    return True, ''


def increment_quota(user_id: str, feature: str):
    """Increment the used_runs counter after a run starts successfully."""
    from qengine.models.User import get_user_by_id
    from qengine.models.UserQuota import UserQuota

    user = get_user_by_id(user_id)
    if not user or user.role == 'admin':
        return  # admin has no quotas to track

    UserQuota.update(
        used_runs=UserQuota.used_runs + 1,
        updated_at=jh.now_to_timestamp(True)
    ).where(
        UserQuota.user_id == user_id,
        UserQuota.feature == feature
    ).execute()
