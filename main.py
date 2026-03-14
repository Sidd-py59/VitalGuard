"""
VitalGuard — FastAPI Application
Serves the dashboard and streams vitals via WebSocket.
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from simulator import WearableSimulator
from risk_engine import compute_risk
from agents import run_agent
from actions import get_twilio_status

app = FastAPI(title="VitalGuard", version="1.0.0")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def no_cache_static(request, call_next):
    """Add no-cache headers to all /static/* responses."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/twilio-status")
async def twilio_status():
    return JSONResponse(get_twilio_status())


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket endpoint for real-time vitals streaming.
    Sends JSON messages with types: vitals, risk, decision, action, error.
    Receives mode-change commands from the frontend.
    """
    await ws.accept()
    simulator = WearableSimulator()
    running = True
    current_location = {"lat": None, "lng": None}

    async def listen_for_commands():
        nonlocal running, current_location
        try:
            while running:
                data = await ws.receive_text()
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "set_mode":
                        mode = msg.get("mode", "normal")
                        if mode in ("normal", "mild_anomaly", "critical_emergency", "auto"):
                            simulator.set_mode(mode)
                            await ws.send_json({
                                "type": "system",
                                "message": f"Scenario mode changed to: {mode.replace('_', ' ').title()}",
                            })
                    elif msg.get("type") == "location_update":
                        current_location = msg.get("location", {"lat": None, "lng": None})
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            running = False
        except Exception:
            running = False

    async def monitoring_loop():
        nonlocal running
        try:
            while running:
                vitals_obj = simulator.generate()
                vitals = vitals_obj.to_dict()
                await ws.send_json({"type": "vitals", "data": vitals})

                risk_assessment = compute_risk(vitals_obj)
                risk = risk_assessment.to_dict()
                await ws.send_json({"type": "risk", "data": risk})

                try:
                    agent_result = await asyncio.wait_for(
                        run_agent(vitals, risk, current_location),
                        timeout=30.0,
                    )
                    await ws.send_json({"type": "decision", "data": agent_result})

                    if "action_result" in agent_result:
                        await ws.send_json({
                            "type": "action",
                            "data": agent_result["action_result"],
                        })

                except asyncio.TimeoutError:
                    await ws.send_json({
                        "type": "decision",
                        "data": {
                            "vitals": vitals,
                            "risk": risk,
                            "clinical_analysis": "[Agent timeout] Vitals recorded. Risk assessment available.",
                            "decided_action": "log" if risk["score"] <= 60 else "alert_user",
                            "action_reasoning": "Agent pipeline timed out — using deterministic fallback.",
                            "action_result": {
                                "action_type": "log",
                                "success": True,
                                "message": "Fallback: reading logged.",
                            },
                        },
                    })
                except Exception as e:
                    await ws.send_json({
                        "type": "error",
                        "message": f"Agent error: {str(e)}",
                    })

                await asyncio.sleep(1)

        except WebSocketDisconnect:
            running = False
        except Exception:
            running = False

    listener_task = asyncio.create_task(listen_for_commands())
    monitor_task = asyncio.create_task(monitoring_loop())

    try:
        await asyncio.gather(listener_task, monitor_task, return_exceptions=True)
    finally:
        running = False
        listener_task.cancel()
        monitor_task.cancel()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)