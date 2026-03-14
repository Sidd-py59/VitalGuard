# VitalGuard: A Comprehensive Knowledge Base

**Welcome to the VitalGuard project.** 
Whether you are a new developer, a non-technical stakeholder, or an AI agent learning this project from scratch, this document contains *everything* you need to know about what VitalGuard is, how it works, and why it is built this way.

---

## What is VitalGuard? (The Simple Explanation)

Imagine a very smart smartwatch that never sleeps. It constantly checks your heart rate, your blood oxygen level, your body temperature, and your stress levels. 

Normally, a smartwatch just shows you these numbers on a screen. But **VitalGuard** is different. It acts like having a doctor and an emergency dispatcher inside the watch. 

If your heart rate spikes or your oxygen drops dangerously low, VitalGuard doesn't just beep at you. It:
1. **Analyzes the data** using an intelligent AI brain to understand *why* this is happening and *how dangerous* it is.
2. **Makes a decision** on what to do (e.g., just log it, text you a warning, book a doctor appointment, or immediately call an ambulance).
3. **Takes real-world action** by actually sending SMS text messages or making voice phone calls to your designated emergency contact, while instantly sending them a Google Maps link of your exact global location.

---

## How it Works: The Journey of a Heartbeat

To understand the system, let's follow the journey of a single piece of data (like a heartbeat) through the application from start to finish.

### Step 1: The Sensor (The Simulator)
In a real-world scenario, a physical watch would gather data from your wrist. Because we are building software, we use a **Simulator** (`simulator.py`). 
Every single second, this simulator generates realistic human vital signs:
* **Heart Rate (bpm):** How fast your heart is beating.
* **SpO2 (%):** How much oxygen is in your blood.
* **Temperature (°C):** Your body heat.
* **HRV (ms):** Heart Rate Variability (a measure of stress/fatigue).

*The user can click buttons on the Dashboard to tell the simulator: "Act like the patient is having a heart attack right now."*

### Step 2: The First Checkpoint (The Risk Engine)
Before waking up the AI brain, the data passes through a quick checklist called the **Risk Engine** (`risk_engine.py`).
This is a standard calculator. It looks at the numbers and says: *"A heart rate of 150 is bad. I will give this a Risk Score of 85 out of 100."*
It labels the situation as LOW, MODERATE, HIGH, or CRITICAL to save time. 

### Step 3: The AI Brain (The LangGraph Agent)
This is where the magic happens. The data (and the risk score) is handed over to an Artificial Intelligence pipeline (`agents.py`). We use a system called **LangGraph** which organizes the AI's thoughts into a 4-step thinking process, like an assembly line:

1. **Vitals Analyzer:** The AI looks at the raw numbers and writes a quick medical summary. Example: *"The patient has a severely elevated heart rate but oxygen levels are normal."*
2. **Anomaly Detector:** The AI looks deeper. *"Given the high risk score, this is an abnormal and urgent situation."* (If the person is perfectly healthy, the AI skips this step to save energy).
3. **Decision Maker:** The AI decides what to do in the real world based on the emergency. It chooses one of these four actions:
   * `log`: Do nothing, just write it down in the database.
   * `alert_user`: Send a mild text message to the patient.
   * `schedule_doctor`: Automatically tell the system to book a medical appointment.
   * `call_emergency`: The situation is dire—contact family/emergency services immediately!
4. **Action Executor:** Hands the final decision over to the real-world communication system.

### Step 4: Real-World Action (The Actions Dispatcher)
The **Action Dispatcher** (`actions.py`) executes the AI's final decision. 
If the AI yelled *"CALL EMERGENCY!"*, this module connects to a real telecommunications service called **Twilio**. 
It will:
1. Grab the patient's real-time GPS coordinates from their web browser.
2. Formulate a Google Maps Link (e.g., `https://maps.google.com/?q=40.7128,-74.0060`).
3. Send a real SMS Text Message to the emergency contact's phone.
4. Place an automated Robot Voice Call to the emergency contact's phone saying: *"Warning! Patient is experiencing a critical health event."*

*(Note: It has a "cooldown" timer of 60 seconds so it doesn't accidentally spam the emergency contact with hundreds of texts!)*

### Step 5: The Dashboard (The Frontend)
While all of this happens in milliseconds in the background, a beautiful, live Dashboard (`main.py` and `static/app.js`) is updating on the user's screen.
Lines on a graph wiggle up and down to show the heart rate, a gauge fills up with red if the risk score is high, and a scrolling text box shows the AI's exact thoughts and actions as they happen in real-time. 

---

## File Dictionary: Where does everything live?

If you are an AI agent analyzing this codebase, or a developer looking to fix a bug, here is the exact map of the project files:

| File Name | Extension | Purpose (What does it do?) |
| :--- | :--- | :--- |
| **`main.py`** | Python | **The Central Train Station.** This is the server (built with FastAPI). It turns on the website, holds open the continuous connection (WebSocket) to the browser, and shuttles data back and forth between the Simulator, the AI, and the User Interface. |
| **`simulator.py`** | Python | **The Fake Patient.** Generates the fake heartbeats and temperature numbers every second. |
| **`risk_engine.py`** | Python | **The Calculator.** Applies strict mathematical rules to calculate a 0-100 danger score. |
| **`agents.py`** | Python | **The AI Brain.** Connects to the local `llama 3.1` model. It contains the 4-step LangGraph thinking pipeline (Analyze -> Detect -> Decide -> Execute). |
| **`actions.py`** | Python | **The Megaphone.** Connects to Twilio. It handles actually sending the SMS texts, placing the Voice Calls, formatting the Google Maps location links, and managing "cooldown" timers to prevent spam. |
| **`config.py`** & **`.env`**| Python/Text | **The Secrets Vault.** Stores sensitive passwords and phone numbers required for Twilio to send texts to phones. |
| **`static/index.html`**| HTML | **The Canvas.** The basic structural skeleton of the dashboard webpage. |
| **`static/style.css`**| CSS | **The Paint.** Makes the dashboard look beautiful, modern, dark-themed, and responsive. |
| **`static/app.js`** | JavaScript | **The Puppeteer.** Runs inside the user's web browser. It draws the wiggling charts, asks the browser for GPS location access, connects to `main.py` via WebSocket, and instantly updates the screen when new data arrives. |

---

## Technical Details (For AI Agents and Developers)

* **Communication Protocol:** The backend and frontend communicate almost exclusively via **WebSockets**. The frontend does not constantly ask for data (HTTP Polling). Instead, the backend pushes data down the websocket pipe every 1 second continuously.
* **AI Model Hosting:** The AI is not hosted in the cloud (like ChatGPT). It runs entirely on the local computer using a tool called **Ollama** running the `llama3.1:8b` model. Because it runs locally, it is private and does not require an internet connection for the reasoning logic.
* **Fallbacks (Mock System):** If Twilio is disabled, or if the user removes their phone numbers, the system will NOT crash. `actions.py` will catch the missing data, generate a completely realistic fake message, print it to the backend terminal, and label it as `{"mode": "mock"}` so the UI can still display what *would* have been sent.
* **Location Tracking Lifecycle:**
    1. `app.js` requests the user's `navigator.geolocation`.
    2. Over the WebSocket, `app.js` sends `{ "type": "location_update", "lat": 12.3, "lng": 45.6 }`.
    3. `main.py` intercepts this and holds it in the `current_location` state variable.
    4. When a heartbeat happens, `current_location` is passed into `agents.py`, which eventually passes it to `actions.py`.
    5. `actions.py` extracts the coordinates and bolts them onto the SMS body.

---

## Setup & Running the Project

1. **Credentials**: Fill out `.env` with Twilio API keys and target phone numbers. Ensure `TWILIO_ENABLED=true` is set.
2. **AI Backend**: Install Ollama and ensure the model is downloaded and running:
   ```bash
   ollama pull llama3.1:8b
   ollama run llama3.1:8b
   ```
3. **Start the Web Server**:
   ```bash
   python main.py
   ```
4. **View**: Open `http://localhost:8000` in a modern browser. 
5. **Permissions**: You MUST click "Allow" when the browser asks for Location permissions, otherwise the SMS messages will say "Location: Unknown".
