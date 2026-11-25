"""
Builds and runs the matching graph (step 3).
"""
from app.graph.state import MatchState
from langgraph.graph import StateGraph, END, START
from app.graph.nodes import extract_profile, extract_offer
from app.schemas import MatchInitialResponse

# Entra desde el endpoint POST de /match aquí, trae el cv y la oferta
def build_graph(cv_text: str, offer_text: str):

    workflow = StateGraph(MatchState)
    
    workflow.add_node("extract_profile", extract_profile)
    workflow.add_node("extract_offer", extract_offer)

    workflow.add_edge(START, "extract_profile")
    workflow.add_edge(START, "extract_offer")

    workflow.add_edge("extract_profile", END)
    workflow.add_edge("extract_offer", END)

    final_graph = workflow.compile()
    initial_input = {
        "cv_text": cv_text,
        "offer_text": offer_text,
        "log": []
    }
    final_exec = final_graph.invoke(initial_input)
    return MatchInitialResponse(
        thread_id="provisional",   # luego vendrá del checkpointer
        profile=final_exec["profile"],
    )