import os
import time
import csv
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from pypdf import PdfReader

# Import modular base configurations
from state import AgentState
import prompts

load_dotenv()

if not os.getenv("GROQ_API_KEY") or not os.getenv("LANGCHAIN_API_KEY"):
    raise ValueError("CRITICAL: Missing API keys. Ensure GROQ_API_KEY and LANGCHAIN_API_KEY are configured.")

# Initialize LLM Base Layer
llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.0)

# ==========================================
# REUSABLE ENGINE NODES
# ==========================================

def ingestion_agent(state: AgentState) -> dict:
    print("\n[Node 1] Ingestion Agent: Scanning 'incoming_files' folder...")
    current_count = state.get("current_loop_count", 0) + 1
    folder_path = "incoming_files"
    extracted_text = ""
    
    target_filename = state.get("current_file")
    if not target_filename:
        raise ValueError("CRITICAL: No target filename was provided in the AgentState!")
        
    target_file = os.path.join(folder_path, target_filename)
    print(f" -> Processing active file: {target_file}")
    
    if target_file.endswith(".txt"):
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                extracted_text = f.read()
        except UnicodeDecodeError:
            with open(target_file, "r", encoding="cp1252") as f:
                extracted_text = f.read()
    elif target_file.endswith(".pdf"):
        reader = PdfReader(target_file)
        for page in reader.pages:
            text = page.extract_text()
            if text: extracted_text += text + "\n"
            
    return {"raw_documents": [extracted_text], "current_loop_count": current_count}


def financial_analyst_agent(state: AgentState) -> dict:
    print(f"[Node 2] Financial Analyst Agent: Processing text via Base Engine...")
    current_count = state.get("current_loop_count", 0)
    print(f" -> Current Loop Attempt: {current_count}")
    
    raw_doc = state["raw_documents"][0]
    feedback = state.get("feedback_for_analyst", "None")
    
    user_prompt = f"Raw Text: {raw_doc}\nCompliance Audit Feedback to address: {feedback}"
    response = llm.invoke([SystemMessage(content=prompts.ANALYST_SYSTEM_PROMPT), HumanMessage(content=user_prompt)])
    
    try:
        extracted_data = eval(response.content.strip())
    except:
        extracted_data = {"revenue": 0, "expenses": 0, "net_profit": 0}
        
    print(f" -> Engine Extracted Data: {extracted_data}")
    return {"extracted_financials": extracted_data, "current_loop_count": current_count}


def compliance_auditor_agent(state: AgentState) -> dict:
    print("[Node 3] Compliance Auditor Agent: Executing rule validation...")
    financials = state["extracted_financials"]
    current_count = state.get("current_loop_count", 0) + 1
    
    user_prompt = f"Verify these extracted numbers: {financials}"
    response = llm.invoke([SystemMessage(content=prompts.AUDITOR_SYSTEM_PROMPT), HumanMessage(content=user_prompt)])
    audit_result = response.content.strip()

    errors = []
    feedback = ""
    
    if "PASSED" not in audit_result.upper():
        print(f" -> !! AUDIT FAILED: {audit_result}")
        errors.append("Compliance Discrepancy")
        feedback = f"Your previous generation yielded {financials}. Rule validation failed. Details: {audit_result}. Please correct the state."
    else:
        print(" -> SUCCESS: Workflow rules validated perfectly.")

    return {
        "compliance_errors": errors, 
        "feedback_for_analyst": feedback,
        "current_loop_count": current_count
    }


def human_review_node(state: AgentState) -> dict:
    print("\n⚠️ [HUMAN INTERVENTION NODE] ⚠️")
    print(f"The AI could not resolve data compliance for file: {state['current_file']}.")
    print(f"Current broken extraction: {state['extracted_financials']}")
    print("Please manually correct the metrics below to clear this document:")
    
    rev = int(input("Enter Correct Revenue (Integer): "))
    exp = int(input("Enter Correct Expenses (Integer): "))
    prof = int(input("Enter Correct Net Profit (Integer): "))
    
    return {
        "extracted_financials": {"revenue": rev, "expenses": exp, "net_profit": prof},
        "compliance_errors": [],
        "feedback_for_analyst": "Manually cleared by human operator."
    }


def report_generator_agent(state: AgentState) -> dict:
    print("[Node 4] Report Generator Agent: Outputting final data delivery...")
    financials = state["extracted_financials"]
    
    user_prompt = f"{prompts.REPORT_GENERATOR_PROMPT} {financials}"
    response = llm.invoke([HumanMessage(content=user_prompt)])
    final_report_text = response.content.strip()
    
    csv_filename = "audited_financials_ledger.csv"
    file_exists = os.path.exists(csv_filename)
    
    with open(csv_filename, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Revenue", "Expenses", "Net Profit", "Executive Summary"])
            
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([
            current_time,
            financials.get("revenue", 0),
            financials.get("expenses", 0),
            financials.get("net_profit", 0),
            final_report_text
        ])
    print(f" -> Logged verified metrics perfectly to '{csv_filename}'.")
    return {"final_report": final_report_text}


# ==========================================
# DETERMINISTIC SYSTEM ROUTING
# ==========================================

def route_based_on_compliance(state: AgentState) -> str:
    if len(state.get("compliance_errors", [])) == 0:
        print(" -> [Router] Compliance clean! Routing directly to Report Generator.")
        return "generate_report"
        
    if state.get("current_loop_count", 0) >= 3:
        print(f" -> [Circuit Breaker Triggered] Loop count is {state['current_loop_count']} with unresolved errors. Escallating to HUMAN REVIEW.")
        return "human_intervention"
        
    print(f" -> [Router] Error detected (Attempt {state['current_loop_count']}/3). Rerouting back for self-correction.")
    return "re_evaluate"


# Graph Assembly
workflow = StateGraph(AgentState)

workflow.add_node("IngestData", ingestion_agent)
workflow.add_node("AnalyzeFinancials", financial_analyst_agent)
workflow.add_node("AuditCompliance", compliance_auditor_agent)
workflow.add_node("HumanReview", human_review_node)
workflow.add_node("CompileReport", report_generator_agent)

workflow.set_entry_point("IngestData")
workflow.add_edge("IngestData", "AnalyzeFinancials")
workflow.add_edge("AnalyzeFinancials", "AuditCompliance")

workflow.add_conditional_edges(
    "AuditCompliance",
    route_based_on_compliance,
    {
        "re_evaluate": "AnalyzeFinancials", 
        "generate_report": "CompileReport",
        "human_intervention": "HumanReview"
    }
)

workflow.add_edge("HumanReview", "AuditCompliance")
workflow.add_edge("CompileReport", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

if __name__ == "__main__":
    print("--- Starting Production-Grade Modular Multi-Agent Engine ---")
    folder_path = "incoming_files"
    
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        print(f"Created empty '{folder_path}' folder. Please drop files inside!")
        exit()
        
    files_to_process = [f for f in os.listdir(folder_path) if f.endswith(('.txt', '.pdf'))]
    if not files_to_process:
        print(f"No valid files found in '{folder_path}'.")
        exit()
        
    print(f" -> Found {len(files_to_process)} file(s) to process in batch queue.")
    print("=" * 60)

    for index, filename in enumerate(files_to_process, start=1):
        print(f"\n🚀 PROCESSING FILE {index}/{len(files_to_process)}: {filename}")
        print("-" * 50)
        
        config = {"configurable": {"thread_id": f"file_session_{filename}"}}
        initial_inputs = {
            "raw_documents": [], 
            "current_loop_count": 0, 
            "feedback_for_analyst": "",
            "current_file": filename
        }
        
        try:
            final_state = app.invoke(initial_inputs, config=config)
            print(f"\n--- Final Result for {filename} ---")
            print(final_state["final_report"])
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ Critical Error processing {filename}: {e}")
            print("=" * 60)
            continue
            
    print("\n[System] All files in batch processed successfully. Cooling down telemetry...")