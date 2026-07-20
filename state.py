from typing import TypedDict, List

class AgentState(TypedDict):
    raw_documents: List[str]
    extracted_financials: dict
    compliance_errors: List[str]
    final_report: str
    current_loop_count: int
    feedback_for_analyst: str
    current_file: str  # <--- Add this line to track the active file