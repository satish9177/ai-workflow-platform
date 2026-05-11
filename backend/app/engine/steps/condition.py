import re
from typing import Any

from simpleeval import EvalWithCompoundTypes


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
    result = evaluate_condition(step["expression"], context)
    branch = "if_true" if result else "if_false"
    return {
        "branch": branch,
        "next_step": step.get(branch),
        "result": result,
    }
