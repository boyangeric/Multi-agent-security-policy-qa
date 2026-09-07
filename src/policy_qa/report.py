"""Human-readable presentation of query traces for the CLI.

Kept apart from the Typer commands so the report format is testable and the
CLI module stays a thin command layer. JSON output bypasses this entirely via
`QueryTrace.to_dict`.
"""

from __future__ import annotations

import textwrap

from .config import Settings
from .tracing import QueryTrace

WIDTH = 80


def wrap_text(body: str, width: int = WIDTH) -> str:
    """Wrap each line to the banner width, preserving list indentation."""
    lines: list[str] = []
    for raw in body.splitlines():
        stripped = raw.lstrip()
        indent = raw[: len(raw) - len(stripped)]
        if not stripped:
            lines.append("")
            continue
        lines.extend(
            textwrap.wrap(
                stripped,
                width=width,
                initial_indent=indent,
                subsequent_indent=indent + "  ",
            )
        )
    return "\n".join(lines)


def render_report(trace: QueryTrace, settings: Settings) -> str:
    """Format a completed query trace as a compliance-style report."""
    answer = trace.answer
    if answer.grounded and not trace.fallback_reason:
        status = "SUCCESS"
    else:
        reason = trace.fallback_reason or "ungrounded"
        status = f"FALLBACK ({reason})"

    citations = ", ".join(answer.citations) or "-"
    grounding = f"{'VERIFIED' if answer.grounded else 'UNVERIFIED'} (Grounded: {answer.grounded})"

    out: list[str] = []
    out.append("=" * WIDTH)
    out.append("MULTI-AGENT SECURITY POLICY Q&A")
    out.append("=" * WIDTH)
    out.append(f"User Query : {trace.question}")
    out.append(f"Status     : {status}")
    out.append("-" * WIDTH)
    out.append("")
    out.append("ANSWER: ")
    out.append("")
    out.append(wrap_text(answer.answer))
    out.append("")
    out.append("-" * WIDTH)
    out.append("📊 RETRIEVAL & GROUNDING TELEMETRY")
    out.append("-" * WIDTH)
    out.append(f"[+] Source Citations : {citations}")
    out.append(f"[+] Grounding Status : {grounding}")
    out.append(f"[+] Confidence Level : {answer.confidence.upper()}")
    out.append(f"[+] Latency Profile  : {trace.duration_ms:,} ms")

    quality: list[str] = []
    if trace.reranked and trace.reranked.relevance_scores:
        scores = trace.reranked.relevance_scores.values()
        avg = sum(scores) / len(scores)
        quality.append(f"    - Context Relevance : {avg:.2f} (avg graded relevance)")
    if trace.faithfulness:
        score = trace.faithfulness[-1]["faithfulness_score"]
        quality.append(f"    - Faithfulness Score: {score:.2f} (higher is more grounded)")
    if quality:
        out.append("[+] Quality Metrics  :")
        out.extend(quality)

    out.append("")
    out.append(f"[i] Detailed inputs/outputs have been written to: {settings.log_file}")
    out.append("=" * WIDTH)
    return "\n".join(out)
