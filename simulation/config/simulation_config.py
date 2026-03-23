"""Simulation configuration for r/SaaS Reddit simulation.

MiroFish-style time-based scheduling: 1 round = 1 simulated hour.
Agents are randomly activated each round based on time-of-day multipliers
and per-archetype activity levels.
"""

PLATFORM_CONFIG = {
    "recsys_type": "reddit",
    "allow_self_rating": False,
    "show_score": True,
    "max_rec_post_len": 20,
    "refresh_rec_post_count": 5,
}

TIME_CONFIG = {
    "total_hours": 4,
    "minutes_per_round": 30,
    "start_hour": 9,
    "agents_per_hour_min": 1,
    "agents_per_hour_max": 2,
    "peak_hours": [9, 10, 11, 14, 15, 20, 21, 22],
    "peak_multiplier": 1.5,
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "off_peak_multiplier": 0.1,
    "normal_multiplier": 0.7,
}

ARCHETYPE_NAMES = [
    "saas_founder_early",
    "saas_founder_scaled",
    "skeptical_pm",
    "indie_hacker",
    "hr_people_ops",
    "lurker",
    "community_regular",
    "vc_growth",
]

ACTIVITY_CONFIGS = {
    "saas_founder_early": {
        "activity_level": 0.6,
        "active_hours": list(range(7, 23)),
        "vote_probability": 0.8,
    },
    "saas_founder_scaled": {
        "activity_level": 0.4,
        "active_hours": list(range(8, 21)),
        "vote_probability": 0.6,
    },
    "skeptical_pm": {
        "activity_level": 0.5,
        "active_hours": list(range(9, 22)),
        "vote_probability": 0.4,
    },
    "indie_hacker": {
        "activity_level": 0.4,
        "active_hours": list(range(8, 24)),
        "vote_probability": 0.7,
    },
    "hr_people_ops": {
        "activity_level": 0.4,
        "active_hours": list(range(9, 18)),
        "vote_probability": 0.7,
    },
    "lurker": {
        "activity_level": 0.2,
        "active_hours": list(range(0, 24)),
        "vote_probability": 0.9,
    },
    "community_regular": {
        "activity_level": 0.5,
        "active_hours": list(range(8, 23)),
        "vote_probability": 0.5,
    },
    "vc_growth": {
        "activity_level": 0.3,
        "active_hours": list(range(9, 20)),
        "vote_probability": 0.6,
    },
}
