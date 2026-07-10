from __future__ import annotations

from typing import Any, Callable

from pydantic_ai.mcp import MCPToolset

from gamebook_web.harness.adventure_structure import CheckStep, ParamSpec
from gamebook_web.mcp_host import call_engine


def resolve_template_value(value: Any, resolve_ctx: dict[str, Any]) -> Any:
    """Resolve a `"${a.b}"`-shaped template value against `resolve_ctx` via a
    closed, structured dotted-path lookup. Not `eval()`/`exec()` — a literal
    (non-`${...}`) value passes through unchanged (ADR-033 structural
    requirement 1).
    """
    if not isinstance(value, str) or not (value.startswith("${") and value.endswith("}")):
        return value
    path = value[2:-1]
    obj: Any = resolve_ctx
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
}


def clamp_params(raw: dict[str, Any], spec: dict[str, ParamSpec]) -> dict[str, Any]:
    """Bound classifier-supplied param values to the matched template's
    declared `ParamSpec` — the schema clamps/rejects, it never lets an
    unbounded value through, regardless of what the classifier proposed.
    """
    resolved: dict[str, Any] = {}
    for name, param_spec in spec.items():
        value = raw.get(name)
        if param_spec.type == "int":
            lo = param_spec.min if param_spec.min is not None else 0
            hi = param_spec.max if param_spec.max is not None else lo
            value = value if isinstance(value, int) else lo
            resolved[name] = max(lo, min(hi, value))
        elif param_spec.type == "enum":
            values = param_spec.values or []
            resolved[name] = value if value in values else (values[0] if values else None)
        else:
            resolved[name] = value
    return resolved


async def run_check_step(
    step: CheckStep,
    *,
    toolset: MCPToolset,
    campaign_id: str,
    resolve_ctx: dict[str, Any],
    checks_log: list[dict[str, Any]],
) -> None:
    """Execute one `CheckStep` (and recursively its `on_success`/`on_failure`
    branch) via `call_engine()` — zero LLM calls, matching ADR-033's
    "deterministic dispatcher (code, 0 LLM calls)" diagram exactly.
    """
    args = {k: resolve_template_value(v, resolve_ctx) for k, v in step.args.items()}
    result = await call_engine(toolset, step.tool, campaign_id=campaign_id, **args)
    checks_log.append({"tool": step.tool, "args": args, "result": result})

    next_ctx = dict(resolve_ctx)
    next_ctx["result"] = result
    if isinstance(result, dict):
        for key in ("skill", "stamina", "luck"):
            if key in result:
                next_ctx[key] = result[key]

    if step.comparator is not None:
        op = step.comparator.get("op")
        left = resolve_template_value(step.comparator.get("left"), next_ctx)
        right = resolve_template_value(step.comparator.get("right"), next_ctx)
        passed = COMPARATORS[op](left, right)
    elif isinstance(result, dict) and "success" in result:
        passed = bool(result["success"])
    else:
        passed = True

    for sub_step in (step.on_success if passed else step.on_failure):
        await run_check_step(
            sub_step,
            toolset=toolset,
            campaign_id=campaign_id,
            resolve_ctx=next_ctx,
            checks_log=checks_log,
        )
