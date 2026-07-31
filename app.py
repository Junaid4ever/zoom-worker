# In master_app.py, inside /api/kill-meeting:

for project in PROJECTS:
    project_results = []
    # Send 50 stop requests per worker (to cover 42 replicas)
    for attempt in range(50):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{project['url']}/api/stop-bots",
                    json={"meeting_code": meeting_code}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    killed = data.get("bots_killed_local", 0)
                    project_results.append(killed)
                else:
                    project_results.append(0)
        except Exception:
            project_results.append(0)
        await asyncio.sleep(0.1)  # 100ms delay for speed
    # ...
