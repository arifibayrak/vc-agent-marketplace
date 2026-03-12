import os

from rich.console import Console

console = Console()

_client = None
_model = None
_fallback_mode = False


def init_llm():
    """Initialize the Anthropic client. Falls back to pre-written responses if no API key."""
    global _client, _model, _fallback_mode

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    _model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

    if not api_key:
        _fallback_mode = True
        console.print("[yellow]No ANTHROPIC_API_KEY found. Using fallback responses.[/yellow]")
        return

    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=api_key)
        _fallback_mode = False
        console.print(f"[green]LLM initialized: {_model}[/green]")
    except Exception as e:
        _fallback_mode = True
        console.print(f"[yellow]LLM init failed ({e}). Using fallback responses.[/yellow]")


async def think(system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
    """Ask the LLM to generate a response. Falls back to a placeholder if no API key."""
    if _fallback_mode or not _client:
        return _fallback_response(user_prompt)

    try:
        response = _client.messages.create(
            model=_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
    except Exception as e:
        console.print(f"[yellow]LLM call failed ({e}). Using fallback.[/yellow]")
        return _fallback_response(user_prompt)


_fallback_call_count = 0


def _fallback_response(prompt: str) -> str:
    """Generate pre-written responses based on context keywords."""
    global _fallback_call_count
    _fallback_call_count += 1
    prompt_lower = prompt.lower()

    # Investment decision - check FIRST because decision prompts also contain "pitch" in context
    if "make an investment decision" in prompt_lower or ("decide" in prompt_lower and "interest or pass" in prompt_lower):
        if _fallback_call_count % 2 == 0:
            return (
                '{"decision": "interest", '
                '"reasoning": "Strong technical team with defensible IP and impressive early traction. '
                'The market opportunity is large and the unit economics are trending in the right direction.", '
                '"next_steps": "Schedule a partner meeting to discuss terms and conduct deeper technical due diligence."}'
            )
        else:
            return (
                '{"decision": "pass", '
                '"reasoning": "While the team is talented and the product shows promise, '
                'the current metrics are too early for our investment criteria. '
                'We would be interested in reconnecting once monthly revenue exceeds $100K.", '
                '"next_steps": null}'
            )

    # Introduction message from VC to startup
    if "introduction" in prompt_lower or ("interest" in prompt_lower and "fit" in prompt_lower):
        return (
            "We have been tracking your space closely and believe your approach is compelling. "
            "Our fund has deep experience in your sector and we would love to learn more about your traction."
        )

    # Pitch generation by startup
    if "pitch" in prompt_lower or "elevator" in prompt_lower:
        return (
            "We are solving a critical problem in our industry with a unique, technology-driven approach. "
            "Our team has deep domain expertise and we have achieved strong early traction with paying customers. "
            "We are seeking funding to accelerate growth and expand into new markets. "
            "Our competitive advantage lies in our proprietary technology and first-mover position."
        )

    # Due diligence questions from VC
    if "3 critical" in prompt_lower or ("question" in prompt_lower and "due diligence" in prompt_lower):
        return (
            '["What is your current monthly burn rate and runway?", '
            '"Who are your top 3 competitors and what differentiates you?", '
            '"What does your customer acquisition funnel look like and what is your CAC?"]'
        )

    # Answers from startup
    if "answer" in prompt_lower and "question" in prompt_lower:
        return (
            "Our monthly burn rate is approximately $150K with 18 months of runway. "
            "We differentiate from competitors through our proprietary technology stack and deeper integrations. "
            "Our primary acquisition channel is direct sales with a CAC of approximately $2,500, "
            "which we recover within 3 months given our average contract value."
        )

    return "Thank you for the information. We will review and follow up shortly."
