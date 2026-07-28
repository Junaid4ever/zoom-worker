from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import asyncio
import os
import random
import base64
import gc
from datetime import datetime
from playwright.async_api import async_playwright
import nest_asyncio
import uvicorn

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
# INDIAN NAMES
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
    bot_count: int
    duration_minutes: int = 5

# ============================================
# BOT FUNCTION (FIXED VERSION - YOUR WORKING SCRIPT)
# ============================================
async def start_bot(tag, wait_time, meetingcode, passcode):
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Starting browser...")
        
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
                    '--max_old_space_size=256',
                    '--js-flags=--max-old-space-size=256',
                    '--disable-site-isolation-trials',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disk-cache-size=0',
                    '--media-cache-size=0'
                ]
            )

            context = await browser.new_context(
                viewport={"width": 800, "height": 600},
                permissions=[],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            page = await context.new_page()
            zoom_url = get_zoom_url(meetingcode)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Navigating to Zoom...")
            await page.goto(zoom_url, timeout=60000)
            await asyncio.sleep(2)

            # ============================================
            # NAME INPUT - EXACTLY AS YOUR WORKING SCRIPT
            # ============================================
            try:
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
                            user_name = get_indian_name()
                            await name_input.first.fill(user_name)
                            name_filled = True
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Name entered: {user_name}")
                            break
                    except:
                        continue
                
                if not name_filled:
                    await page.keyboard.type(get_indian_name())
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Name typed")
                    
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Name error: {e}")

            # ============================================
            # PASSCODE INPUT - EXACTLY AS YOUR WORKING SCRIPT
            # ============================================
            if passcode and passcode != "" and passcode != "0":
                try:
                    await asyncio.sleep(0.5)
                    passcode_xpath = '/html/body/div[2]/div[1]/div/div[1]/div/div[2]/div[2]/div/input'
                    pass_input = page.locator(f'xpath={passcode_xpath}')
                    if await pass_input.count() > 0:
                        await pass_input.fill(passcode)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Passcode entered")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Passcode error: {e}")

            # ============================================
            # JOIN BUTTON - EXACTLY AS YOUR WORKING SCRIPT
            # ============================================
            try:
                join_xpath = '/html/body/div[2]/div[1]/div/div[1]/div/div[2]/button'
                join_btn = page.locator(f'xpath={join_xpath}')
                if await join_btn.count() > 0:
                    await join_btn.click()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Join button clicked")
                else:
                    await page.keyboard.press('Enter')
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Enter pressed for join")
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Join error: {e}")
                await page.keyboard.press('Enter')

            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Joined successfully!")

            # ============================================
            # AUDIO JOIN - AS PER YOUR WORKING SCRIPT
            # ============================================
            try:
                await asyncio.sleep(2)
                audio_selectors = [
                    '//button[contains(text(), "Join Audio")]',
                    '//button[contains(text(), "Join with Computer Audio")]',
                    '//button[contains(@class, "audio-join")]',
                    '//span[contains(text(), "Join Audio")]/parent::button'
                ]
                
                audio_joined = False
                for selector in audio_selectors:
                    try:
                        audio_btn = page.locator(f'xpath={selector}')
                        if await audio_btn.count() > 0:
                            await audio_btn.first.click()
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Audio join clicked")
                            audio_joined = True
                            break
                    except:
                        continue
                
                if not audio_joined:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - No audio join button found")
                    
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Audio join error: {e}")

            # ============================================
            # STAY IN MEETING - EXACTLY AS YOUR WORKING SCRIPT
            # ============================================
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Staying in meeting for {wait_time//60} minutes")
            
            elapsed = 0
            while elapsed < wait_time:
                await asyncio.sleep(10)
                elapsed += 10
                
                if elapsed % 60 == 0:
                    try:
                        await page.evaluate("() => 'ping'")
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Keep alive ping {elapsed//60}m")
                    except:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Ping failed")
                        break

            print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Done")
            
            await page.close()
            await context.close()
            await browser.close()
            gc.collect()
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} - Failed: {str(e)[:200]}")

# ============================================
# API ENDPOINTS
# ============================================
@app.get("/")
async def root():
    return {"message": "Zoom Bot API is running!", "status": "healthy"}

@app.post("/api/start-bots")
async def start_bots(request: StartBotRequest):
    try:
        if request.bot_count < 1 or request.bot_count > 5:
            raise HTTPException(status_code=400, detail="Bot count must be between 1 and 5")
        
        # Start bots in background
        def run_bots():
            asyncio.run(run_bot_tasks(request.meeting_code, request.passcode, request.bot_count, request.duration_minutes))
        
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
        task = asyncio.create_task(start_bot(tag, duration_seconds, meeting_code, passcode))
        tasks.append(task)
        await asyncio.sleep(0.3)
    
    await asyncio.gather(*tasks)

# ============================================
# RUN
# ============================================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
