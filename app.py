from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import asyncio
import sys
import base64
import random
import os
import time
import psutil
import gc
import signal
from datetime import datetime
from playwright.async_api import async_playwright
import nest_asyncio
import uvicorn
from typing import List, Optional

nest_asyncio.apply()

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# NAME GENERATORS
# ============================================
INDIAN_FIRST_NAMES = [
    'Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun', 'Reyansh', 'Ayaan', 'Krishna', 'Ishaan', 'Shaurya',
    'Rahul', 'Rohan', 'Priya', 'Ananya', 'Diya', 'Saanvi', 'Aadhya', 'Kavya', 'Riya', 'Anika',
    'Amit', 'Rajesh', 'Sneha', 'Pooja', 'Neha', 'Vikram', 'Karan', 'Manish', 'Suresh', 'Deepak'
]
INDIAN_LAST_NAMES = [
    'Sharma', 'Verma', 'Patel', 'Kumar', 'Singh', 'Reddy', 'Gupta', 'Joshi',
    'Malhotra', 'Mehta', 'Chopra', 'Khanna', 'Agarwal', 'Jain', 'Saxena',
    'Bansal', 'Srivastava', 'Mishra', 'Pandey', 'Rao', 'Desai', 'Nair'
]

ENGLISH_FIRST_NAMES = [
    'James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph',
    'Thomas', 'Charles', 'Christopher', 'Daniel', 'Matthew', 'Anthony', 'Donald',
    'Mark', 'Paul', 'Steven', 'Andrew', 'Kenneth', 'Joshua', 'Kevin', 'Brian',
    'George', 'Timothy', 'Ronald', 'Edward', 'Jason', 'Jeffrey', 'Ryan', 'Jacob'
]
ENGLISH_LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
    'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Wilson', 'Anderson', 'Thomas',
    'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White',
    'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Walker', 'Young'
]

def get_indian_name():
    return f"{random.choice(INDIAN_FIRST_NAMES)} {random.choice(INDIAN_LAST_NAMES)}"

def get_english_name():
    return f"{random.choice(ENGLISH_FIRST_NAMES)} {random.choice(ENGLISH_LAST_NAMES)}"

def get_name(name_type, custom_names=None, index=0):
    if name_type == "custom" and custom_names and index < len(custom_names):
        return custom_names[index]
    elif name_type == "english":
        return get_english_name()
    else:
        return get_indian_name()

# ============================================
# ZOOM URL
# ============================================
ZOOM_PARTS = {
    'domain': base64.b64decode('em9vbS51cw==').decode(),
    'join_path': base64.b64decode('d2Mvam9pbg==').decode()
}

def get_zoom_url(meeting_code):
    return f"https://{ZOOM_PARTS['domain']}/{ZOOM_PARTS['join_path']}/{meeting_code}"

# ============================================
# REQUEST MODELS
# ============================================
class StartBotRequest(BaseModel):
    meeting_code: str
    passcode: str = ""
    bot_count: int = 50
    duration_minutes: int = 60
    name_type: str = "indian"
    custom_names: Optional[List[str]] = None

class StopBotRequest(BaseModel):
    meeting_code: str

# ============================================
# STATE
# ============================================
active_contexts = {}  # tag -> context
active_meetings = {}
billing_enabled = True
shared_browser = None
browser_lock = asyncio.Lock()

# ============================================
# SYNC BARRIER (GLOBALS — FIXED)
# ============================================
READY_TO_JOIN = asyncio.Event()
BOTS_READY = 0
BOTS_TOTAL = 0
BOTS_FAILED = 0
BOTS_LOCK = asyncio.Lock()

# ============================================
# SHARED BROWSER
# ============================================
async def get_shared_browser(playwright):
    global shared_browser
    async with browser_lock:
        if shared_browser is None:
            shared_browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--disable-extensions',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-features=PermissionPrompt',
                    '--disable-notifications',
                    '--disable-popup-blocking',
                    '--disable-camera',
                    '--disable-video-capture',
                    '--mute-audio',
                    '--use-fake-device-for-media-stream',
                    '--use-file-for-fake-audio-capture=/dev/null',
                    '--window-size=800,600',
                    '--max_old_space_size=256',
                    '--js-flags=--max-old-space-size=256',
                    '--disable-site-isolation-trials',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disk-cache-size=0',
                    '--media-cache-size=0'
                ]
            )
        return shared_browser

# ============================================
# WAIT FOR ALL BOTS (USES GLOBAL SYNC VARIABLES)
# ============================================
async def wait_for_all_bots(meeting_code):
    global BOTS_READY, BOTS_TOTAL, BOTS_FAILED
    async with BOTS_LOCK:
        BOTS_READY += 1
        ready = BOTS_READY
        total = BOTS_TOTAL
        failed = BOTS_FAILED

    print(f"[SYNC] {ready}/{total} bots ready (failed: {failed})")

    if ready + failed >= total:
        READY_TO_JOIN.set()
        print("⚡ All bots ready! Joining together...")

    await READY_TO_JOIN.wait()

# ============================================
# KILL FUNCTION
# ============================================
def kill_all_browser_processes(meeting_code):
    killed = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if ('chromium' in cmdline.lower() or 'chrome' in cmdline.lower()) and meeting_code in cmdline:
                proc.kill()
                killed += 1
        except:
            pass
    return killed

async def kill_meeting_browsers_local(meeting_code):
    killed = 0
    tags = list(active_contexts.keys())
    for tag in tags:
        if tag.startswith(meeting_code):
            try:
                await active_contexts[tag].close()
                killed += 1
            except:
                pass
            del active_contexts[tag]
    killed += kill_all_browser_processes(meeting_code)
    return killed

# ============================================
# BOT FUNCTION
# ============================================
async def start_bot(tag, wait_time, meetingcode, passcode, name_type, custom_names, index, playwright):
    global BOTS_FAILED
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Started")
    gc.collect()

    try:
        browser = await get_shared_browser(playwright)

        context = await browser.new_context(
            viewport={"width": 800, "height": 600},
            permissions=[],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        active_contexts[tag] = context

        page = await context.new_page()
        zoom_url = get_zoom_url(meetingcode)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Navigating to Zoom...")
        await page.goto(zoom_url, timeout=60000)
        await asyncio.sleep(1)

        # NAME INPUT
        try:
            user_name = get_name(name_type, custom_names, index)
            name_selectors = [
                '//*[@id="input-for-name"]',
                '//input[@placeholder="Enter your name"]',
                '//input[@name="name"]'
            ]
            
            name_filled = False
            for selector in name_selectors:
                try:
                    name_input = page.locator(f'xpath={selector}')
                    if await name_input.count() > 0:
                        await name_input.first.wait_for(state="visible", timeout=2000)
                        await name_input.first.fill(user_name)
                        name_filled = True
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Name entered: {user_name}")
                        break
                except:
                    continue
            
            if not name_filled:
                await page.keyboard.type(user_name)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Name typed: {user_name}")
                
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Name error: {e}")

        # PASSCODE INPUT
        if passcode and passcode != "" and passcode != "0":
            try:
                await asyncio.sleep(0.3)
                passcode_xpath = '/html/body/div[2]/div[1]/div/div[1]/div/div[2]/div[2]/div/input'
                pass_input = page.locator(f'xpath={passcode_xpath}')
                if await pass_input.count() > 0:
                    await pass_input.fill(passcode)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Passcode entered")
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Passcode error: {e}")

        # WAIT FOR ALL BOTS (USES GLOBAL SYNC)
        await wait_for_all_bots(meetingcode)

        # JOIN BUTTON
        try:
            join_xpath = '/html/body/div[2]/div[1]/div/div[1]/div/div[2]/button'
            join_btn = page.locator(f'xpath={join_xpath}')
            if await join_btn.count() > 0:
                await join_btn.click()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Join clicked")
            else:
                await page.keyboard.press('Enter')
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Enter pressed for join")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Join error: {e}")
            await page.keyboard.press('Enter')

        await asyncio.sleep(1)
        
        # Audio join
        try:
            audio_btn = page.locator('xpath=//button[contains(text(), "Join Audio")]')
            if await audio_btn.count() > 0:
                await audio_btn.click()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Audio joined")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Audio error: {e}")

        await asyncio.sleep(1)
        try:
            leave_btn = page.locator('xpath=//button[contains(text(), "Leave")]')
            if await leave_btn.count() > 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} ✅ CONFIRMED: In meeting!")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} ⚠️ Not confirmed in meeting")
        except:
            pass

        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} ✅ Joined! Staying for {wait_time//60} minutes")
        
        elapsed = 0
        while elapsed < wait_time:
            await asyncio.sleep(10)
            elapsed += 10
            
            if elapsed % 60 == 0:
                gc.collect()
                try:
                    await page.evaluate("() => 'ping'")
                except:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} Ping failed")
                    break

        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} ✅ Done")
        
        await page.close()
        await context.close()
        gc.collect()
        
        if tag in active_contexts:
            del active_contexts[tag]
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} ❌ Failed: {str(e)[:100]}")
        BOTS_FAILED += 1
        if tag in active_contexts:
            del active_contexts[tag]

# ============================================
# API ENDPOINTS
# ============================================
@app.get("/")
async def root():
    return {"message": "Zoom Bot Worker is running!", "status": "healthy"}

@app.post("/api/start-bots")
async def start_bots(request: StartBotRequest):
    global BOTS_TOTAL, BOTS_READY, BOTS_FAILED, billing_enabled
    
    if not billing_enabled:
        raise HTTPException(status_code=403, detail="Billing is disabled")
    
    try:
        if request.bot_count < 1 or request.bot_count > 50:
            raise HTTPException(status_code=400, detail="Bot count must be between 1 and 50")
        
        BOTS_TOTAL = request.bot_count
        BOTS_READY = 0
        BOTS_FAILED = 0
        READY_TO_JOIN.clear()
        
        if request.meeting_code not in active_meetings:
            active_meetings[request.meeting_code] = {
                "start_time": datetime.now(),
                "bots": request.bot_count,
                "duration": request.duration_minutes,
                "status": "running"
            }
        else:
            active_meetings[request.meeting_code]["status"] = "running"
        
        def run_bots():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_bot_tasks(
                    request.meeting_code, 
                    request.passcode, 
                    request.bot_count, 
                    request.duration_minutes,
                    request.name_type,
                    request.custom_names
                ))
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_bots)
        thread.daemon = True
        thread.start()
        
        return {
            "success": True,
            "message": f"Started {request.bot_count} bots for meeting {request.meeting_code}",
            "duration": request.duration_minutes
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def run_bot_tasks(meeting_code, passcode, bot_count, duration_minutes, name_type, custom_names):
    duration_seconds = duration_minutes * 60
    async with async_playwright() as p:
        tasks = []
        for i in range(bot_count):
            tag = f"{meeting_code}-Bot-{i+1}"
            task = asyncio.create_task(
                start_bot(tag, duration_seconds, meeting_code, passcode, name_type, custom_names, i, p)
            )
            tasks.append(task)
            await asyncio.sleep(0.15)
        
        await asyncio.gather(*tasks)
        
        global shared_browser
        if shared_browser:
            await shared_browser.close()
            shared_browser = None
    
    if meeting_code in active_meetings:
        active_meetings[meeting_code]["status"] = "completed"
        active_meetings[meeting_code]["completed_at"] = datetime.now().isoformat()

# ============================================
# STOP ENDPOINT
# ============================================
@app.post("/api/stop-bots")
async def stop_bots(request: StopBotRequest):
    meeting_code = request.meeting_code
    killed = await kill_meeting_browsers_local(meeting_code)
    if meeting_code in active_meetings:
        active_meetings[meeting_code]["status"] = "killed"
    global shared_browser
    if shared_browser:
        await shared_browser.close()
        shared_browser = None
    return {
        "success": True,
        "message": f"Killed {killed} bots.",
        "bots_killed_local": killed
    }

@app.get("/api/status")
async def get_status():
    return {
        "billing_enabled": billing_enabled,
        "active_meetings": active_meetings,
        "running_bots": len(active_contexts)
    }

@app.get("/health")
async def health():
    return {
        "online": True,
        "capacity": 50,
        "worker_id": "worker"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
