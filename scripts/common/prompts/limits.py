"""Condition-neutral run limits, separate from lead-only organization prompts."""


def limit_instructions(timeout, web_limit=0):
    """Condition-neutral run limits, stated identically to Single and Subagents."""
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise ValueError("Run limits require a positive integer timeout in seconds")
    if isinstance(web_limit, bool) or not isinstance(web_limit, int) or web_limit < 0:
        raise ValueError("Web request limit must be a non-negative integer")
    duration = f"{timeout} seconds" + (f" ({timeout // 60} minutes)" if timeout % 60 == 0 else "")
    text = f"Run limits: {duration} of wall-clock time in total"
    if web_limit:
        text += (f", and at most {web_limit} web search/fetch requests in total, shared by every agent and process "
                 "in this run (each web helper response reports how many remain)")
    return text + ". Do not try to work around tool limits or network restrictions.\n"
