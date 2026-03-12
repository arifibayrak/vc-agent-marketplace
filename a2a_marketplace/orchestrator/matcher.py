"""Matching algorithm — scores startup-VC fit (0.0 to 1.0)."""


def compute_match_score(vc_profile: dict, startup_profile: dict) -> float:
    """Score a startup against a VC's investment criteria.

    Weights:
        - Sector match: 0.4
        - Stage match: 0.3
        - Check size fit: 0.2
        - Metrics quality: 0.1
    """
    score = 0.0

    # Sector match (0.4)
    target_sectors = vc_profile.get("target_sectors", [])
    startup_sector = startup_profile.get("sector", "")
    if startup_sector in target_sectors:
        score += 0.4

    # Stage match (0.3)
    target_stages = vc_profile.get("target_stages", [])
    startup_stage = startup_profile.get("stage", "")
    if startup_stage in target_stages:
        score += 0.3

    # Check size fit (0.2)
    check_min = vc_profile.get("check_size_min", 0)
    check_max = vc_profile.get("check_size_max", float("inf"))
    funding_ask = startup_profile.get("funding_ask", 0)
    if check_min <= funding_ask <= check_max:
        score += 0.2

    # Metrics quality bonus (0.1)
    metrics = startup_profile.get("metrics", {})
    if metrics.get("mrr", 0) > 0:
        score += 0.05
    if metrics.get("growth_rate", 0) > 0:
        score += 0.03
    if metrics.get("customers", 0) > 0:
        score += 0.02

    return round(score, 2)
