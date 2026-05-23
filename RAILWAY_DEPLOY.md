# ModelTrack on Railway — Deployment Guide

## Free Tier (No Payment Needed)

Railway's free tier gives you **$5/month** in free credits — more than enough for ModelTrack.

**Important:** Free tier is not available during peak hours (8 AM – 8 PM Pacific Time). Deploy during off-peak hours (evening/night PST).

---

## Deploy to Railway (From Your Phone)

### Step 1: Create a New Project
1. Go to **railway.app** on your phone
2. Sign in with **GitHub** (use your credentials)
3. Tap **"Create New Project"**
4. Select **"Deploy from GitHub repo"**

### Step 2: Authorize GitHub
1. If prompted, tap **"Authorize Railway on GitHub"**
2. After auth, you'll see a list of your repos
3. Find and tap **`ShreyasKhandare/modeltrack`**
4. Confirm to deploy from the repo

### Step 3: Configure the Deployment
1. Railway will auto-detect:
   - `railway.toml` (configuration)
   - `docker/Dockerfile` (build instructions)
   - `init_db.py` (database initialization)

2. Under **"Environment"** (if visible), add:
   ```
   DATABASE_URL = sqlite:///./modeltrack.db
   ```
   (Or leave blank — it defaults to SQLite)

### Step 4: Deploy
1. Tap the **Deploy** button
2. Watch the build logs:
   - "Initialization" → "Build" → "Deploy" → "Healthcheck"
3. Wait ~3-5 minutes for the full build and startup

### Step 5: Get Your Live URL
Once deployed, Railway shows your app URL:
```
https://modeltrack-[random-id].railway.app
```

Test it:
- **API Root:** `https://modeltrack-[id].railway.app/`
- **Health Check:** `https://modeltrack-[id].railway.app/health`
- **API Docs:** `https://modeltrack-[id].railway.app/docs` (interactive Swagger UI)
- **Lineage Graph:** `https://modeltrack-[id].railway.app/pipelines/example/lineage`

---

## Troubleshooting

### "Free tier not available during peak hours"
- **Cause:** You're deploying between 8 AM – 8 PM Pacific Time
- **Fix:** Wait until evening (after 8 PM PT) or early morning (before 8 AM PT)
- **Current time:** Check `time.is/Los_Angeles` to see Pacific Time

### "Healthcheck failed"
- **Cause:** The container is crashing or taking >60s to start
- **Fix:** Check the deployment logs (Railway shows them in real-time)
  - Look for errors in "Build" or "Deploy" phase
  - If DB error: ensure `init_db.py` ran successfully
  - If import error: check Python dependencies in `requirements.txt`

### "Port binding error"
- **Cause:** The app is trying to bind to port 8000 but Railway assigns a different port
- **Fix:** This is already fixed in our code:
  - `docker/Dockerfile` uses `$PORT` env var
  - `init_db.py` doesn't need a port
  - Uvicorn automatically uses the Railway-provided port

---

## What's Running After Deployment

Your live ModelTrack instance includes:

**REST API** (on `https://modeltrack-[id].railway.app`)
- `GET /` — API info
- `GET /health` — Health check
- `POST /pipelines/{name}/run` — Execute pipelines
- `GET /models/{name}/versions` — List model versions
- `POST /models/{name}/register` — Register new models
- `POST /ab-tests/` — Start A/B tests
- `GET /docs` — Full API documentation (Swagger UI)

**Database** (SQLite)
- Automatically initialized on container startup
- Stores: pipeline runs, models, A/B test results

**Storage Directories** (in container)
- `/app/models_store/` — Saved model binaries
- `/app/pipelines_store/` — Pipeline definitions
- `./modeltrack.db` — SQLite database

---

## Keeping Your App Running

Railway's free tier:
- ✅ Runs 24/7 (no sleep/wake)
- ✅ $5/month free credit (covers typical usage)
- ✅ Auto-restart on crash
- ✅ Health checks every 30s

**No action needed** — just deploy and it runs.

---

## Next Steps After Deploy

Once your live URL is ready:

1. **Test the API**
   ```bash
   curl https://modeltrack-[id].railway.app/health
   ```

2. **Try the Swagger UI**
   - Go to `https://modeltrack-[id].railway.app/docs`
   - Try running a pipeline or registering a model interactively

3. **Share the URL**
   - Your portfolio-ready live ModelTrack instance
   - Show to interviewers: "Live API running on Railway"

---

## Cost Breakdown (Free Tier)

| Resource | Monthly Usage | Cost |
|----------|---------------|------|
| CPU | ~86 vCPU-minutes | ~$0.04 |
| Memory | ~1,488 GB-minutes | ~$3.44 |
| Egress | 0 GB | $0.00 |
| **Total** | — | **~$3.49** |

You get **$5/month free**, so you're well within limits. ✅

---

## Questions?

- **Railway docs:** https://docs.railway.app
- **ModelTrack repo:** https://github.com/ShreyasKhandare/modeltrack
- **GitHub Issues:** Create an issue in the repo for bugs
