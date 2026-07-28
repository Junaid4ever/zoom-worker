from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import asyncio
import os
import random
import base64
import gc
import time
from datetime import datetime
from playwright.async_api import async_playwright
import nest_asyncio
import uvicorn
from pathlib import Path
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
# SCREENSHOT DIRECTORY
# ============================================
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================
# INDIAN NAME GENERATOR
# ============================================
INDIAN_FIRST_NAMES = [
    'Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun', 'Reyansh', 'Ayaan', 
    'Krishna', 'Ishaan', 'Shaurya', 'Rahul', 'Rohan', 'Priya', 'Ananya',
    'Diya', 'Saanvi', 'Aadhya', 'Kavya', 'Riya', 'Anika', 'Amit', 'Rajesh',
    'Sneha', 'Pooja', 'Neha', 'Vikram', 'Karan', 'Manish', 'Suresh', 'Deepak'
]

INDIAN_LAST_NAMES = [
    'Sharma', 'Verma', 'Patel', 'Kumar', 'Singh', 'Reddy', 'Gupta', 'Joshi',
    'Malhotra', 'Mehta', 'Chopra', 'Khanna', 'Agarwal', 'Jain', 'Saxena',
    'Bansal', 'Srivastava', 'Mishra', 'Pandey', 'Rao', 'Desai', 'Nair'
]

def get_indian_name():
    return f"{random.choice(INDIAN_FIRST_NAMES)} {random.choice(INDIAN_LAST_NAMES)}"

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
# REQUEST MODEL
# ============================================
class StartBotRequest(BaseModel):
    meeting_code: str
    passcode: str = ""
    bot_count: int = 5
    duration_minutes: int = 10

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
# POPUP HANDLER
# ============================================
async def handle_popups(page, tag):
    try:
        cookie_selectors = [
            '//button[contains(text(), "Accept")]',
            '//button[contains(text(), "Accept All")]',
            '//button[contains(text(), "Allow")]',
            '//button[contains(@class, "accept")]',
            '//button[@id="onetrust-accept-btn-handler"]'
        ]
        
        for selector in cookie_selectors:
            try:
                cookie_btn = page.locator(f'xpath={selector}')
                if await cookie_btn.count() > 0:
                    await cookie_btn.first.click()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - 🍪 Cookies accepted")
                    await asyncio.sleep(0.3)
                    break
            except:
                continue

        try:
            await page.mouse.click(100, 100)
        except:
            pass

    except Exception:
        pass

# ============================================
# OPTIMIZED BOT FUNCTION
# ============================================
async def start_optimized(tag, wait_time, meetingcode, passcode):
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

            context = await browser.new_context(
                viewport={"width": 800, "height": 600},
                permissions=[],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )

            page = await context.new_page()
            zoom_url = get_zoom_url(meetingcode)
            
            await page.goto(zoom_url, timeout=60000)
            await asyncio.sleep(2)
            
            await handle_popups(page, tag)

            # NAME INPUT
            try:
                user_name = get_indian_name()
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
                            await name_input.first.wait_for(state="visible", timeout=3000)
                            await name_input.first.fill(user_name)
                            name_filled = True
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Name: {user_name}")
                            break
                    except:
                        continue
                
                if not name_filled:
                    await page.keyboard.type(user_name)
                    
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Name error: {e}")

            # PASSCODE INPUT
            if passcode and passcode != "" and passcode != "0":
                try:
                    await asyncio.sleep(0.5)
                    passcode_xpath = '/html/body/div[2]/div[1]/div/div[1]/div/div[2]/div[2]/div/input'
                    pass_input = page.locator(f'xpath={passcode_xpath}')
                    if await pass_input.count() > 0:
                        await pass_input.fill(passcode)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Passcode entered")
                except Exception:
                    pass

            # WAIT FOR ALL BOTS
            await wait_for_all_bots()

            # JOIN BUTTON
            try:
                join_xpath = '/html/body/div[2]/div[1]/div/div[1]/div/div[2]/button'
                join_btn = page.locator(f'xpath={join_xpath}')
                if await join_btn.count() > 0:
                    await join_btn.click()
                else:
                    await page.keyboard.press('Enter')
            except Exception:
                await page.keyboard.press('Enter')

            await asyncio.sleep(3)
            await handle_popups(page, tag)
            
            try:
                audio_btn = page.locator('xpath=//button[contains(text(), "Join Audio")]')
                if await audio_btn.count() > 0:
                    await audio_btn.click()
            except Exception:
                pass

            await asyncio.sleep(2)
            try:
                leave_btn = page.locator('xpath=//button[contains(text(), "Leave")]')
                if await leave_btn.count() > 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - ✅ CONFIRMED: In meeting!")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - ⚠️ Not confirmed")
            except:
                pass

            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - ✅ Joined! Staying for {wait_time//60} minutes")
            
            elapsed = 0
            while elapsed < wait_time:
                await asyncio.sleep(10)
                elapsed += 10
                
                if elapsed % 60 == 0:
                    gc.collect()
                    try:
                        await page.evaluate("() => 'ping'")
                    except:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Ping failed")
                        break

            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - ✅ Done")
            
            await page.close()
            await context.close()
            await browser.close()
            gc.collect()
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Failed: {str(e)[:100]}")
        BOTS_FAILED += 1

# ============================================
# API ENDPOINTS
# ============================================
@app.get("/")
async def root():
    return {"message": "Zoom Bot Worker is running!", "status": "healthy"}

@app.post("/api/start-bots")
async def start_bots(request: StartBotRequest):
    global BOTS_TOTAL, BOTS_READY, BOTS_FAILED
    try:
        if request.bot_count < 1 or request.bot_count > 5:
            raise HTTPException(status_code=400, detail="Bot count must be between 1 and 5")
        
        BOTS_TOTAL = request.bot_count
        BOTS_READY = 0
        BOTS_FAILED = 0
        READY_TO_JOIN.clear()
        
        def run_bots():
            asyncio.run(run_bot_tasks(
                request.meeting_code, 
                request.passcode, 
                request.bot_count, 
                request.duration_minutes
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

async def run_bot_tasks(meeting_code, passcode, bot_count, duration_minutes):
    duration_seconds = duration_minutes * 60
    tasks = []
    for i in range(bot_count):
        tag = f"Bot-{i+1}"
        task = asyncio.create_task(
            start_optimized(tag, duration_seconds, meeting_code, passcode)
        )
        tasks.append(task)
        await asyncio.sleep(1.5)
    
    await asyncio.gather(*tasks)

@app.get("/health")
async def health():
    return {
        "online": True,
        "capacity": 5,
        "worker_id": "worker"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)