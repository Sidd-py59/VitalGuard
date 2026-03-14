"""
VitalGuard — LangGraph Agent Pipeline
4-node clinical reasoning chain:
  vitals_analyzer → anomaly_detector → decision_maker → action_executor
Uses Ollama llama3.1:8b via langchain-ollama.
"""

import json
import logging
from typing import Optional, TypedDict

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from actions import execute_action

logger = logging.getLogger("vitalguard.agents")


class AgentState(TypedDict):
    vitals: dict
    risk: dict
    location: dict
    clinical_analysis: str
    anomaly_assessment: str
    decided_action: str
    action_reasoning: str
    action_result: dict
    full_log: dict


def get_llm():
    return ChatOllama(
        model="llama3.1:8b",
        temperature=0.3,
        num_predict=300,
        base_url="http://127.0.0.1:11434",
    )


# ---------------------------
# VITALS ANALYZER
# ---------------------------

async def vitals_analyzer(state: AgentState) -> dict:
    llm = get_llm()
    vitals = state["vitals"]
    risk = state["risk"]

    prompt = f"""You are a clinical health monitoring AI. Analyze these patient vitals:

Heart Rate: {vitals['heart_rate']} bpm (normal: 60-100)
SpO2: {vitals['spo2']}% (normal: 95-100%)
Temperature: {vitals['temperature']}°C (normal: 36.1-37.2°C)
HRV: {vitals['hrv']} ms (normal: 20-70 ms)

Risk Score: {risk['score']}/100 ({risk['level']})
Factors: {', '.join(risk.get('contributing_factors', [])) or 'None'}

Provide a concise clinical interpretation in 2-3 sentences."""

    try:
        response = await llm.ainvoke([
            SystemMessage(content="You are a medical AI assistant providing concise clinical interpretations."),
            HumanMessage(content=prompt),
        ])
        analysis = response.content
    except Exception as e:
        logger.warning(f"Vitals analyzer LLM call failed: {e}")
        analysis = (
            f"[LLM unavailable: {type(e).__name__}] HR={vitals['heart_rate']:.0f}, "
            f"SpO2={vitals['spo2']:.1f}%, Temp={vitals['temperature']:.1f}°C, "
            f"HRV={vitals['hrv']:.1f}. Risk {risk['score']}/100."
        )

    return {"clinical_analysis": analysis}


# ---------------------------
# ANOMALY DETECTOR
# ---------------------------

async def anomaly_detector(state: AgentState) -> dict:
    risk = state["risk"]

    if risk["score"] <= 30:
        return {"anomaly_assessment": "No significant anomalies detected."}

    llm = get_llm()

    prompt = f"""You are a medical anomaly detection AI.

Clinical Analysis:
{state['clinical_analysis']}

Risk Score: {risk['score']}/100

Explain if the situation is concerning and how urgent it is."""

    try:
        response = await llm.ainvoke([
            SystemMessage(content="You are a medical anomaly detection AI."),
            HumanMessage(content=prompt),
        ])
        assessment = response.content
    except Exception as e:
        logger.warning(f"Anomaly detector LLM call failed: {e}")
        assessment = (
            f"[LLM unavailable: {type(e).__name__}] Risk score {risk['score']}/100. "
            f"Factors: {'; '.join(risk.get('contributing_factors', []))}"
        )

    return {"anomaly_assessment": assessment}


# ---------------------------
# DECISION MAKER
# ---------------------------

async def decision_maker(state: AgentState) -> dict:
    risk = state["risk"]
    score = risk["score"]

    if score <= 30:
        return {
            "decided_action": "log",
            "action_reasoning": f"Risk score {score}/100 is LOW. Normal vitals."
        }

    if score >= 81:
        return {
            "decided_action": "call_emergency",
            "action_reasoning": (
                f"CRITICAL condition triggered by: "
                f"{'; '.join(risk.get('contributing_factors', []))}"
            ),
        }

    if score >= 61:
        return {
            "decided_action": "schedule_doctor",
            "action_reasoning": (
                f"HIGH risk condition detected. "
                f"Factors: {'; '.join(risk.get('contributing_factors', []))}. "
                f"Booking doctor appointment automatically."
            ),
        }

    llm = get_llm()

    prompt = f"""You are a medical decision AI.

Clinical Analysis:
{state['clinical_analysis']}

Risk Score: {score}/100

Choose action from:
log, alert_user, schedule_doctor, call_emergency

Respond JSON:
{{"action": "...", "reasoning": "..."}}
"""

    try:
        response = await llm.ainvoke([
            SystemMessage(content="Respond ONLY with JSON."),
            HumanMessage(content=prompt),
        ])

        text = response.content.strip()
        start = text.find("{")
        end = text.rfind("}") + 1

        parsed = json.loads(text[start:end])
        action = parsed.get("action", "alert_user")
        reasoning = parsed.get("reasoning", "")

    except Exception as e:
        logger.warning(f"Decision maker LLM call failed: {e}")
        action = "schedule_doctor" if score >= 61 else "alert_user"
        reasoning = f"Fallback decision based on risk score. (LLM unavailable: {type(e).__name__})"

    return {
        "decided_action": action,
        "action_reasoning": reasoning,
    }


# ---------------------------
# ACTION EXECUTOR
# ---------------------------

async def action_executor(state: AgentState) -> dict:

    action_type = state["decided_action"]
    vitals = state["vitals"]
    risk = state["risk"]
    reasoning = state["action_reasoning"]
    location = state.get("location", {"lat": None, "lng": None})
    trigger_vitals = risk.get("contributing_factors", [])

    result = await execute_action(action_type, vitals, risk, reasoning, location, trigger_vitals)

    result_dict = result.to_dict()

    if action_type == "call_emergency":
        contact_result = await execute_action(
            "notify_contact",
            vitals,
            risk,
            reasoning,
            location,
            trigger_vitals,
        )
        result_dict["contact_notification"] = contact_result.to_dict()

    # ---------------------------
    # FINAL EXPLAINABLE LOG
    # ---------------------------

    full_log = {
        "vitals": vitals,

        "risk_score": risk.get("score"),
        "risk_level": risk.get("level"),

        # 🔥 THIS SHOWS WHICH VITALS TRIGGERED THE AGENT
        "trigger_vitals": risk.get("contributing_factors", []),

        "clinical_analysis": state.get("clinical_analysis", ""),
        "anomaly_assessment": state.get("anomaly_assessment", ""),

        "decided_action": action_type,
        "action_reasoning": reasoning,

        "action_result": result_dict,
    }

    return {"action_result": result_dict, "full_log": full_log}


# ---------------------------
# GRAPH CONTROL
# ---------------------------

def should_skip_anomaly(state: AgentState) -> str:
    if state["risk"]["score"] <= 30:
        return "decision_maker"
    return "anomaly_detector"


def build_agent_graph():

    graph = StateGraph(AgentState)

    graph.add_node("vitals_analyzer", vitals_analyzer)
    graph.add_node("anomaly_detector", anomaly_detector)
    graph.add_node("decision_maker", decision_maker)
    graph.add_node("action_executor", action_executor)

    graph.set_entry_point("vitals_analyzer")

    graph.add_conditional_edges(
        "vitals_analyzer",
        should_skip_anomaly,
        {
            "anomaly_detector": "anomaly_detector",
            "decision_maker": "decision_maker",
        },
    )

    graph.add_edge("anomaly_detector", "decision_maker")
    graph.add_edge("decision_maker", "action_executor")
    graph.add_edge("action_executor", END)

    return graph.compile()


agent = build_agent_graph()


# ---------------------------
# RUN AGENT
# ---------------------------

async def run_agent(vitals: dict, risk: dict, location: Optional[dict] = None):

    if location is None:
        location = {"lat": None, "lng": None}

    initial_state: AgentState = {
        "vitals": vitals,
        "risk": risk,
        "location": location,
        "clinical_analysis": "",
        "anomaly_assessment": "",
        "decided_action": "",
        "action_reasoning": "",
        "action_result": {},
        "full_log": {},
    }

    result = await agent.ainvoke(initial_state)

    return result.get("full_log", result)