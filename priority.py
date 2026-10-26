"""Rule-based priority recommendation for TaskFlow.

This is a transparent keyword/urgency scorer. It is NOT a language model and
needs no API key, network access or paid service.
"""
import re
from datetime import date

PRIORITIES = ["Low", "Medium", "High", "Urgent"]

# (regex, weight, human readable label). Each rule counts at most once.
RULES = [
    # --- Urgent-level signals ---
    (r"\bout(?:age|ages)\b", 5, "outage"),
    (r"\bdata (?:loss|leak)\b|\bsecurity (?:breach|incident)\b|\bbreach(?:ed)?\b|\bhack(?:ed)?\b",
     5, "data loss or security incident"),
    (r"\b(?:is|are|went|goes) down\b|\bdown for\b|\bsite down\b|\bserver down\b|\bservice down\b",
     5, "service is down"),
    (r"\basap\b|\bimmediately\b|\bright away\b|\bright now\b|\bemergency\b|\burgent(?:ly)?\b",
     4, "explicit urgency (ASAP/urgent/immediately)"),
    (r"\bcritical\b|\bsev ?[01]\b|\bp0\b|\bblocker\b|\bblocking\b", 4, "critical or blocking issue"),
    (r"\ball users\b|\bevery(?:one| user| customer)\b|\bcustomers? (?:are )?affected\b",
     3, "wide user impact"),
    (r"\bcrash(?:es|ed|ing)?\b", 3, "crashes"),
    (r"\bproduction\b|\bprod\b|\blive site\b", 2, "production environment"),
    # --- High-level signals ---
    (r"\bdeadline\b|\bdue (?:today|tomorrow|tonight)\b|\btoday\b|\btomorrow\b|\btonight\b"
     r"|\bby (?:eod|end of day|end of week|monday|tuesday|wednesday|thursday|friday)\b",
     3, "near-term deadline"),
    (r"\bsecurity\b|\bvulnerab\w*\b", 3, "security concern"),
    (r"\bhigh priority\b", 3, "marked as high priority"),
    (r"\bclients?\b|\bcustomers?\b", 2, "customer-facing"),
    (r"\brevenue\b|\bpayments?\b|\bbilling\b|\bcheckout\b", 2, "revenue or payments"),
    (r"\bbug\b|\bbroken\b|\bfail(?:s|ed|ing|ure)?\b|\berror\b|\bregression\b|\bnot working\b",
     2, "defect or failure"),
    (r"\bimportant\b", 2, "marked as important"),
    (r"\brelease\b|\blaunch\b|\bgo[- ]live\b|\bdemo\b", 2, "upcoming release or demo"),
    # --- Low-level signals ---
    (r"\bnice[- ]to[- ]have\b|\bsomeday\b|\beventually\b|\bwhenever\b|\bwhen (?:you )?(?:have )?time\b"
     r"|\bif time permits\b|\blow priority\b|\bbacklog\b|\boptional\b|\bidea\b",
     -3, "explicitly low urgency"),
    (r"\bclean ?up\b|\brefactor\w*\b|\bdocumentation\b|\bdocs\b|\btypo\b|\bcosmetic\b|\bminor\b"
     r"|\bpolish\b|\brename\b|\btidy\b",
     -2, "routine or minor work"),
]

MODERATE_CAP = 5

NEGATION = re.compile(
    r"\b(?:not|isn't|is not|non)[ -](?:urgent|critical|asap|a rush)\b|\bno rush\b|\bnot a blocker\b"
)


def _due_adjustment(due_date, today):
    if not due_date:
        return 0, None
    try:
        due = date.fromisoformat(str(due_date)[:10])
    except ValueError:
        return 0, None
    days = (due - today).days
    if days < 0:
        return 3, "due date has already passed"
    if days <= 1:
        return 3, "due within 1 day"
    if days <= 3:
        return 2, "due within 3 days"
    if days <= 7:
        return 1, "due within a week"
    if days > 30:
        return -1, "due date is more than a month away"
    return 0, None


def suggest_priority(text, due_date=None, today=None):
    """Return a recommendation dict for the given task description."""
    today = today or date.today()
    lowered = (text or "").lower()
    strong = 0      # weight >= 4: clear emergencies / explicit urgency
    moderate = 0    # weight 2-3: supporting signals, capped so they cannot reach Urgent alone
    lowering = 0    # negative weights
    reasons = []

    if NEGATION.search(lowered):
        lowering -= 4
        reasons.append("says the work is not urgent")
        lowered = NEGATION.sub(" ", lowered)

    for pattern, weight, label in RULES:
        if re.search(pattern, lowered):
            if weight >= 4:
                strong += weight
            elif weight > 0:
                moderate += weight
            else:
                lowering += weight
            reasons.append(label)

    score = strong + min(moderate, MODERATE_CAP) + lowering

    adjustment, label = _due_adjustment(due_date, today)
    if label:
        score += adjustment
        reasons.append(label)

    if score >= 6:
        priority = "Urgent"
    elif score >= 3:
        priority = "High"
    elif score <= -2:
        priority = "Low"
    else:
        priority = "Medium"

    if reasons:
        explanation = f"Recommended {priority} because the description points to: {', '.join(reasons)}."
    else:
        explanation = ("No strong urgency indicators were found, so Medium is the sensible default. "
                       "Add details such as impact, deadlines or affected users for a sharper result.")

    return {
        "priority": priority,
        "score": score,
        "signals": reasons,
        "explanation": explanation,
        "method": "rule-based",
        "disclaimer": "Rule-based keyword recommendation - not an AI language model.",
    }
