HOOK_SCENE_DURATION_EPSILON = 0.001


def hook_scene_newly_exceeds_short_limit(
    *,
    clip_duration: float,
    hook_duration: float,
    short_max_duration: float,
) -> bool:
    maximum = short_max_duration + HOOK_SCENE_DURATION_EPSILON
    return (
        clip_duration <= maximum
        and clip_duration + hook_duration > maximum
    )
