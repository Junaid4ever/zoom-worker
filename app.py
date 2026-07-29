from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import threading
import asyncio
import os
import random
import base64
import gc
import signal
import psutil
from datetime import datetime
from playwright.async_api import async_playwright
import nest_asyncio
import uvicorn
from typing import List, Optional
from pathlib import Path
from faker import Faker

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
# SCREENSHOT DIRECTORY
# ============================================
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================
# ULTRA-FAST NAME GENERATORS
# ============================================

fake_indian = Faker('en_IN')
fake_english = Faker('en_US')

INDIAN_NAME_POOL = []
ENGLISH_NAME_POOL = []

for _ in range(2000):
    INDIAN_NAME_POOL.append(fake_indian.name())
    ENGLISH_NAME_POOL.append(fake_english.name())

def get_indian_name():
    return random.choice(INDIAN_NAME_POOL)

def get_english_name():
    return random.choice(ENGLISH_NAME_POOL)

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
    bot_count: int = 5
    duration_minutes: int = 60
    name_type: str = "indian"
    custom_names: Optional[List[str]] = None

class StopBotRequest(BaseModel):
    meeting_code: str

# ============================================
# STATE
# ============================================
active_browsers = {}  # tag -> browser object
active_browser_pids = {}  # tag -> pid
active_meetings = {}
billing_enabled = True

# ============================================
# SYNC BARRIER
# ============================================
READY_TO_JOIN = asyncio.Event()
BOTS_READY = 0
BOTS_TOTAL = 0
BOTS_FAILED = 0
BOTS_LOCK = asyncio.Lock()

async def wait_for_all_bots():
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
# INSTANT KILL - Force Kill Browser Process
# ============================================
def kill_all_browser_processes(meeting_code):
    """Kill all Chromium processes associated with this meeting using psutil"""
    killed = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'chromium' in cmdline.lower() or 'chrome' in cmdline.lower():
                if meeting_code in cmdline or any(tag.startswith(meeting_code) for tag in active_browser_pids.keys()):
                    proc.kill()
                    killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return killed

async def kill_meeting_browsers(meeting_code):
    """Kill all browsers for a meeting instantly"""
    killed = 0
    tags_to_remove = []
    
    # First, try graceful close via playwright
    for tag, browser in list(active_browsers.items()):
        if tag.startswith(meeting_code):
            try:
                await browser.close()
                killed += 1
                tags_to_remove.append(tag)
            except:
                # If graceful fails, we'll kill via psutil later
                pass
    
    # Remove tags that were closed gracefully
    for tag in tags_to_remove:
        if tag in active_browsers:
            del active_browsers[tag]
        if tag in active_browser_pids:
            del active_browser_pids[tag]
    
    # Force kill any remaining processes using psutil
    killed += kill_all_browser_processes(meeting_code)
    
    # Clean up any remaining tags
    for tag in list(active_browser_pids.keys()):
        if tag.startswith(meeting_code):
            del active_browser_pids[tag]
    for tag in list(active_browsers.keys()):
        if tag.startswith(meeting_code):
            del active_browsers[tag]
    
    return killed

# ============================================
# BOT FUNCTION - WITH DETAILED LOGS
# ============================================
async def start_bot(tag, wait_time, meetingcode, passcode, name_type, custom_names, index):
    global BOTS_FAILED
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Started")
    gc.collect()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
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
                    '--max_old_space_size=64',
                    '--js-flags=--max-old-space-size=64',
                    '--disable-site-isolation-trials',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disk-cache-size=0',
                    '--media-cache-size=0',
                    '--single-process'
                ]
            )

            active_browsers[tag] = browser
            if hasattr(browser, 'process') and browser.process:
                active_browser_pids[tag] = browser.process.pid

            context = await browser.new_context(
                viewport={"width": 800, "height": 600},
                permissions=[],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )

            page = await context.new_page()
            zoom_url = get_zoom_url(meetingcode)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Navigating to Zoom...")
            await page.goto(zoom_url, timeout=60000)
            await asyncio.sleep(1.5)

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
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Name entered: {user_name}")
                            break
                    except:
                        continue
                
                if not name_filled:
                    await page.keyboard.type(user_name)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Name typed: {user_name}")
                    
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Name error: {e}")

            # PASSCODE INPUT
            if passcode is not None and passcode != "":
                try:
                    await asyncio.sleep(0.3)
                    passcode_xpath = '/html/body/div[2]/div[1]/div/div[1]/div/div[2]/div[2]/div/input'
                    pass_input = page.locator(f'xpath={passcode_xpath}')
                    if await pass_input.count() > 0:
                        await pass_input.fill(passcode)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Passcode entered")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Passcode error: {e}")

            # WAIT FOR ALL BOTS
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Waiting for all bots...")
            await wait_for_all_bots()

            # JOIN BUTTON
            try:
                join_xpath = '/html/body/div[2]/div[1]/div/div[1]/div/div[2]/button'
                join_btn = page.locator(f'xpath={join_xpath}')
                if await join_btn.count() > 0:
                    await join_btn.click()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Join clicked")
                else:
                    await page.keyboard.press('Enter')
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Enter pressed for join")
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Join error: {e}")
                await page.keyboard.press('Enter')

            await asyncio.sleep(2)
            
            # Audio join
            try:
                audio_btn = page.locator('xpath=//button[contains(text(), "Join Audio")]')
                if await audio_btn.count() > 0:
                    await audio_btn.click()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Audio joined")
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Audio error: {e}")

            await asyncio.sleep(1)
            try:
                leave_btn = page.locator('xpath=//button[contains(text(), "Leave")]')
                if await leave_btn.count() > 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - CONFIRMED: In meeting!")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Warning: Not confirmed in meeting")
            except:
                pass

            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - ✅ Joined! Staying for {wait_time//60} minutes")
            
            # STAY IN MEETING
            elapsed = 0
            while elapsed < wait_time:
                if not billing_enabled:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Billing disabled, stopping...")
                    break
                    
                await asyncio.sleep(10)
                elapsed += 10
                
                if elapsed % 60 == 0:
                    gc.collect()
                    try:
                        await page.evaluate("() => 'ping'")
                    except:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Ping failed")
                        break

            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Done")
            
            await page.close()
            await context.close()
            await browser.close()
            gc.collect()
            
            if tag in active_browsers:
                del active_browsers[tag]
            if tag in active_browser_pids:
                del active_browser_pids[tag]
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Failed: {str(e)[:100]}")
        BOTS_FAILED += 1
        if tag in active_browsers:
            del active_browsers[tag]
        if tag in active_browser_pids:
            del active_browser_pids[tag]

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
        if request.bot_count < 1 or request.bot_count > 5:
            raise HTTPException(status_code=400, detail="Bot count must be between 1 and 5")
        
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
            asyncio.run(run_bot_tasks(
                request.meeting_code, 
                request.passcode, 
                request.bot_count, 
                request.duration_minutes,
                request.name_type,
                request.custom_names
            ))
        
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
    tasks = []
    for i in range(bot_count):
        tag = f"{meeting_code}-Bot-{i+1}"
        task = asyncio.create_task(
            start_bot(tag, duration_seconds, meeting_code, passcode, name_type, custom_names, i)
        )
        tasks.append(task)
        await asyncio.sleep(0.3)
    
    await asyncio.gather(*tasks)
    
    if meeting_code in active_meetings:
        active_meetings[meeting_code]["status"] = "completed"
        active_meetings[meeting_code]["completed_at"] = datetime.now().isoformat()

@app.post("/api/stop-bots")
async def stop_bots(request: StopBotRequest):
    """Kill all bots for a meeting instantly"""
    meeting_code = request.meeting_code
    
    killed = await kill_meeting_browsers(meeting_code)
    
    if meeting_code in active_meetings:
        active_meetings[meeting_code]["status"] = "killed"
        active_meetings[meeting_code]["killed_at"] = datetime.now().isoformat()
    
    return {
        "success": True,
        "message": f"Instantly killed {killed} bots for meeting {meeting_code}",
        "bots_killed": killed
    }

@app.get("/api/status")
async def get_status():
    return {
        "billing_enabled": billing_enabled,
        "active_meetings": active_meetings,
        "running_bots": len(active_browsers)
    }

@app.get("/health")
async def health():
    return {
        "online": True,
        "capacity": 5,
        "worker_id": "worker"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
