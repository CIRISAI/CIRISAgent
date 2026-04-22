"""Escalation guidance helper."""


def get_escalation_guidance(actions_taken: int, max_actions: int = 7) -> str:
    """Returns escalation guidance string based on actions taken and max allowed."""
    if actions_taken < 3:
        stage = "early"
    elif actions_taken < 5:
        stage = "mid"
    elif actions_taken < max_actions:
        stage = "late"
    else:
        stage = "exhaust"

    messages = {
        "early": "Stage: EARLY — You have plenty of rounds; explore thoroughly and establish context.",
        "mid": "Stage: MID — Over halfway; focus on core principles and clarity.",
        "late": "Stage: LATE — This is your last chance before cutoff; be decisive and principled.",
        "exhaust": "Stage: EXHAUSTED — Max rounds reached; conclude now or abort the task.",
    }
    return messages[stage]
