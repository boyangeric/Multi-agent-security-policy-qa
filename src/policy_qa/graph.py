"""Small, typed Agent Framework workflow for grounded policy Q&A.

The core workflow stages are Planner, Retrieval, and Response. Moderation,
context relevance, and faithfulness are bounded safety gates. No stage loops:
an unfaithful answer goes directly to the deterministic fallback.
"""

from __future__ import annotations

from typing import Any

from agent_framework import Case, Default, Workflow, WorkflowBuilder

from .agents import (
    ContextRelevanceExecutor,
    FaithfulnessGraderExecutor,
    FallbackExecutor,
    MetaKnowledgeExecutor,
    ModerationExecutor,
    PlannerExecutor,
    ResponseExecutor,
    RetrievalExecutor,
    build_deterministic_agent,
)
from .config import Settings
from .prompts import load_prompt
from .schemas import (
    ContentModerationResponse,
    ContextRelevanceGrade,
    FaithfulnessGrade,
    FinalAnswer,
    ModerationVerdict,
    QueryIntent,
    QueryPlan,
    RerankedContext,
)
from .search.search_service import SearchService
from .tracing import TraceState


def moderation_passed(message: Any) -> bool:
    return isinstance(message, ContentModerationResponse) and message.allowed


def is_policy_question(message: Any) -> bool:
    return isinstance(message, QueryPlan) and message.intent is QueryIntent.policy_question


def is_meta_knowledge(message: Any) -> bool:
    return isinstance(message, QueryPlan) and message.intent is QueryIntent.meta_knowledge


def has_reranked_documents(message: Any) -> bool:
    return isinstance(message, RerankedContext) and bool(message.documents)


def build_workflow(
    chat_client: Any,
    search_service: SearchService,
    settings: Settings,
    trace_data: TraceState,
) -> Workflow:
    """Construct the moderated, grounded workflow."""

    def agent(name: str, prompt: str, response_format: type) -> Any:
        return build_deterministic_agent(
            chat_client,
            settings,
            name=name,
            instructions=load_prompt(prompt),
            response_format=response_format,
        )

    moderation = ModerationExecutor(
        agent("moderation", "moderation", ModerationVerdict), trace_data
    )
    planner = PlannerExecutor(agent("planner", "planner", QueryPlan), trace_data)
    retrieval = RetrievalExecutor(search_service, settings, trace_data)
    context_relevance = ContextRelevanceExecutor(
        agent(
            "relevance_grader",
            "context_relevance_grader",
            ContextRelevanceGrade,
        ),
        settings,
        trace_data,
    )
    responder = ResponseExecutor(
        agent("responder", "responder", FinalAnswer), trace_data
    )
    meta_knowledge = MetaKnowledgeExecutor(trace_data)
    faithfulness = FaithfulnessGraderExecutor(
        agent("faithfulness_grader", "faithfulness_grader", FaithfulnessGrade),
        settings,
        trace_data,
    )
    fallback = FallbackExecutor(trace_data)

    return (
        WorkflowBuilder(
            start_executor=moderation,
            max_iterations=settings.workflow_max_iterations,
            output_from="all",
        )
        .add_switch_case_edge_group(
            moderation,
            [
                Case(condition=moderation_passed, target=planner),
                Default(target=fallback),
            ],
        )
        # Intent router: only genuine policy questions pay for the retrieval
        # and grading cycle. Meta questions get a deterministic self-description
        # from the responder; out-of-domain questions terminate at the fallback.
        .add_switch_case_edge_group(
            planner,
            [
                Case(condition=is_policy_question, target=retrieval),
                Case(condition=is_meta_knowledge, target=meta_knowledge),
                Default(target=fallback),
            ],
        )
        .add_edge(retrieval, context_relevance)
        .add_switch_case_edge_group(
            context_relevance,
            [
                Case(condition=has_reranked_documents, target=responder),
                Default(target=fallback),
            ],
        )
        .add_edge(responder, faithfulness)
        # Faithful answers are yielded inside the grader. Only failures are
        # emitted onto this edge and therefore reach the fallback.
        .add_edge(faithfulness, fallback)
        .build()
    )
