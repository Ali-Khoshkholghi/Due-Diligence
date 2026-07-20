# Due Diligence

An autonomous, self-correcting multi-agent pipeline that performs financial due diligence on target-company documents. Built with [LangGraph](https://github.com/langchain-ai/langgraph) and served by a [Groq](https://groq.com/)-hosted LLM (`llama-3.3-70b-versatile`), it ingests raw financial reports, extracts key figures, audits them for internal consistency, self-corrects when the numbers don't add up, escalates to a human when it can't, and produces an audited executive summary.

## How it works

The pipeline is modeled as a cyclic state graph with four agent nodes and one deterministic router:

```
IngestData -> AnalyzeFinancials -> AuditCompliance --(passed)--> CompileReport -> END
                    ^                     |
                    |                (failed, < 3 attempts)
                    +---------------------+
                                          |
                                (failed, >= 3 attempts)
                                          v
                                    HumanReview -> AuditCompliance
```

1. **Ingestion Agent** (`IngestData`) — reads the next queued file from `incoming_files/` (`.txt` or `.pdf`, via `pypdf`) and loads its raw text into state.
2. **Financial Analyst Agent** (`AnalyzeFinancials`) — prompts the LLM to extract `revenue`, `expenses`, and `net_profit` as a structured dict, incorporating any corrective feedback from a prior failed audit.
3. **Compliance Auditor Agent** (`AuditCompliance`) — prompts the LLM to verify that `revenue - expenses == net_profit`. On failure it writes a feedback message describing the discrepancy and increments a loop counter.
4. **Router** (`route_based_on_compliance`) — a deterministic circuit breaker:
   - Compliance clean → straight to `CompileReport`.
   - Compliance failed, fewer than 3 attempts → loop back to `AnalyzeFinancials` for self-correction.
   - Compliance failed, 3+ attempts → escalate to `HumanReview`.
5. **Human Review Node** (`HumanReview`) — a manual CLI checkpoint where an operator types in the correct revenue/expenses/net profit figures to unblock a document the AI couldn't reconcile on its own.
6. **Report Generator Agent** (`CompileReport`) — prompts the LLM for a one-sentence investment recommendation from the cleared figures, then appends a timestamped row (revenue, expenses, net profit, summary) to `audited_financials_ledger.csv`.

Each document is run as its own LangGraph thread (checkpointed in-memory via `MemorySaver`), and `app.py` processes every `.txt`/`.pdf` file found in `incoming_files/` in a batch loop when run directly.

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Graph assembly, agent node implementations, routing logic, and the batch-processing entry point. |
| `prompts.py` | System/user prompt templates for the analyst, auditor, and report-generator LLM calls. |
| `state.py` | The shared `AgentState` `TypedDict` passed between graph nodes. |
| `incoming_files/` | Drop zone for source documents (`.txt` or `.pdf`) to be audited. |
| `audited_financials_ledger.csv` | Append-only output ledger of every successfully audited document. |

## Setup

**Requirements:** Python 3.12, and API keys for Groq and LangChain/LangSmith.

```bash
python3 -m venv venv
source venv/bin/activate
pip install langgraph langchain-groq langchain-core python-dotenv pypdf
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your-groq-api-key
LANGCHAIN_API_KEY=your-langchain-api-key
```

## Usage

1. Drop one or more `.txt` or `.pdf` financial reports into `incoming_files/`.
2. Run the pipeline:

   ```bash
   python app.py
   ```
3. Watch the console for per-document progress, including any self-correction loops or human-review prompts (you'll be asked to type in corrected revenue/expenses/net-profit figures if the AI can't reconcile a document after 3 attempts).
4. Review results appended to `audited_financials_ledger.csv`.

## Notes

- The compliance rule enforced today is a single sanity check: `revenue - expenses == net_profit`. Extend `AUDITOR_SYSTEM_PROMPT` in `prompts.py` to add further rules.
- The analyst's LLM output is parsed with `eval()` on the assumption the model returns a clean Python dict literal; a malformed response falls back to zeroed-out figures rather than crashing the pipeline.
- `audited_financials_ledger.csv` is append-only and accumulates across runs — treat it as a running audit log, not a fresh report per run.
