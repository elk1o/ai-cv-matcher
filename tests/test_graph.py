"""Tests of the graph wiring (app/graph/builder.py and state.py). The nodes are replaced by
fakes: here we check how they are connected, not what they do."""
import pytest
from langgraph.graph import END, START, StateGraph

from app.graph import builder
from app.graph.errors import ExtractionError, ModelQuotaError
from app.graph.state import MatchState
from app.schemas import MatchInitialResponse, Profile, ProfileEntry


def fake_profile_node(calls):
    def node(state):
        calls.append(("extract_profile", state["cv_text"]))
        return {"profile": Profile(skills=[ProfileEntry(title="Python")]), "log": ["perfil"]}
    return node


def fake_offer_node(calls):
    def node(state):
        calls.append(("extract_offer", state["offer_text"]))
        return {"requirements": ["req"], "log": ["oferta"]}
    return node


def test_build_graph_runs_both_branches_with_their_own_text(monkeypatch):
    calls = []
    monkeypatch.setattr(builder, "extract_profile", fake_profile_node(calls))
    monkeypatch.setattr(builder, "extract_offer", fake_offer_node(calls))
    builder.build_graph("texto cv", "texto oferta")
    assert sorted(calls) == [("extract_offer", "texto oferta"), ("extract_profile", "texto cv")]


def test_build_graph_returns_the_extracted_profile(monkeypatch):
    monkeypatch.setattr(builder, "extract_profile", fake_profile_node([]))
    monkeypatch.setattr(builder, "extract_offer", fake_offer_node([]))
    result = builder.build_graph("cv", "oferta")
    assert isinstance(result, MatchInitialResponse)
    assert result.profile.skills[0].title == "Python"
    assert result.thread_id  # provisional for now: it must not be empty


@pytest.mark.parametrize("error", [ExtractionError("fallo"), ModelQuotaError("cuota")])
def test_build_graph_propagates_node_errors_unchanged(monkeypatch, error):
    # The router relies on this: it translates these exceptions into HTTP codes.
    def failing(_state):
        raise error

    monkeypatch.setattr(builder, "extract_profile", fake_profile_node([]))
    monkeypatch.setattr(builder, "extract_offer", failing)
    with pytest.raises(type(error)):
        builder.build_graph("cv", "oferta")


def test_state_log_merges_entries_written_by_parallel_nodes():
    # Without the reducer on `log`, two parallel nodes writing it would conflict (or one would be lost).
    workflow = StateGraph(MatchState)
    workflow.add_node("a", lambda _s: {"log": ["from a"]})
    workflow.add_node("b", lambda _s: {"log": ["from b"]})
    workflow.add_edge(START, "a")
    workflow.add_edge(START, "b")
    workflow.add_edge("a", END)
    workflow.add_edge("b", END)
    final = workflow.compile().invoke({"log": ["start"]})
    assert sorted(final["log"]) == ["from a", "from b", "start"]