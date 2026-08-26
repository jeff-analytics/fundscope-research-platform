PROFILES = {
    'safe': {
        'label': '稳健',
        'holdings': 2,
        'market': 2,
        'security_master': 4,
        'return_gap': 3,
        'major_changes': 2,
    },
    'standard': {
        'label': '标准',
        'holdings': 4,
        'market': 3,
        'security_master': 8,
        'return_gap': 5,
        'major_changes': 3,
    },
    'fast': {
        'label': '极速',
        'holdings': 6,
        'market': 4,
        'security_master': 12,
        'return_gap': 8,
        'major_changes': 4,
    },
}


def normalize_strategy(strategy: str | None) -> str:
    key = str(strategy or 'standard').strip().lower()
    return key if key in PROFILES else 'standard'


def workers_for(task_type: str, strategy: str | None = 'standard', override: int | None = None) -> int:
    task = str(task_type or '').strip()
    if override is not None:
        try:
            n = int(override)
            if n > 0:
                return max(1, min(12, n))
        except Exception:
            pass
    profile = PROFILES[normalize_strategy(strategy)]
    return int(profile.get(task, 1))


def public_profiles():
    return [
        {
            'value': key,
            'label': value['label'],
            'holdings': value['holdings'],
            'market': value['market'],
            'security_master': value['security_master'],
            'return_gap': value['return_gap'],
        }
        for key, value in PROFILES.items()
    ]
