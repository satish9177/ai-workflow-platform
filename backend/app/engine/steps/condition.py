import re
from typing import Any

from simpleeval import EvalWithCompoundTypes

from app.utils.template_renderer import render_template_object


_LENGTH_FILTER_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_\.\[\]'\"]*)\|length")


def _replace_length_filter(match: re.Match[str]) -> str:
    return f"len({match.group(1)})"


def evaluate_condition(expression: str, context: dict[str, Any]) -> bool:
    processed_expression = _LENGTH_FILTER_RE.sub(_replace_length_filter, expression)
    evaluator = EvalWithCompoundTypes(
        names=context,
        functions={"len": len},
    )

    try:
        return bool(evaluator.eval(processed_expression))
    except Exception as exc:
        raise ValueError(f"Invalid condition expression: {expression}") from exc


async def run_condition_step(step: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    expression = step.get("condition") or step.get("expression")
    if not expression:
        raise ValueError("Invalid workflow step: missing condition")
    expression = render_template_object(expression, context)
    result = evaluate_condition(expression, context)
    branch = "if_true" if result else "if_false"
    return {
        "branch": branch,
        "next_step": render_template_object(step.get(branch), context),
        "result": result,
    }
