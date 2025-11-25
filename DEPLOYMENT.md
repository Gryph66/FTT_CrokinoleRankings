# Streamlit Public Site - Deployment Guide

## What's Here

This directory contains everything needed to deploy your **read-only public NCA Rankings site** to Streamlit Community Cloud.

### Files
- `app.py` - Main Streamlit application (simplified, public-only tabs)
- `data/` - Exported JSON data files
- `requirements.txt` - Python dependencies
- `.streamlit/config.toml` - Streamlit configuration
- `README.md` - Public-facing README

## Deployment Steps

### 1. Create GitHub Repository

```bash
cd streamlit_public_site
git init
git add .
git commit -m "Initial commit: NCA Rankings public site"
```

Create a new repository on GitHub (e.g., `nca-rankings-public`), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/nca-rankings-public.git
git branch -M main
git push -u origin main
```

### 2. Deploy to Streamlit Cloud

1. Go to https://share.streamlit.io/
2. Sign in with your GitHub account
3. Click **"New app"**
4. Fill in:
   - **Repository**: `YOUR_USERNAME/nca-rankings-public`
   - **Branch**: `main`
   - **Main file path**: `app.py`
5. Click **"Deploy!"**

### 3. Your Site is Live!

Your site will be available at:
```
https://YOUR_USERNAME-nca-rankings-public.streamlit.app
```

First deployment takes ~2-3 minutes. Subsequent updates deploy in ~1 minute.

## Updating Data

When you update rankings in your admin system:

### Step 1: Export Fresh Data
```bash
cd /Users/shagarty/Downloads/CrokinoleRanker-3
./export_public_site.sh
```

### Step 2: Copy to Public Site
```bash
cp -r public_site_export/data/* streamlit_public_site/data/
```

### Step 3: Commit and Push
```bash
cd streamlit_public_site
git add data/*.json
git commit -m "Update rankings data - $(date +%Y-%m-%d)"
git push
```

### Step 4: Auto-Deploy
Streamlit Cloud automatically detects the push and redeploys in ~1 minute.

## Customization

### Change Theme
Edit `.streamlit/config.toml` to customize colors:
```toml
[theme]
primaryColor = "#FF4B4B"  # Accent color
backgroundColor = "#FFFFFF"  # Main background
secondaryBackgroundColor = "#F0F2F6"  # Sidebar background
textColor = "#262730"  # Text color
```

### Add Custom Domain (Optional)
In Streamlit Cloud settings, you can add a custom domain like `rankings.yourcrokinolesite.com`.

## Monitoring

- **View logs**: Streamlit Cloud dashboard → Your app → "Manage app" → "Logs"
- **Analytics**: Streamlit Cloud shows visitor stats
- **Uptime**: Streamlit Cloud has 99.9% uptime

## Troubleshooting

**App won't start:**
- Check logs in Streamlit Cloud dashboard
- Verify `requirements.txt` has all dependencies
- Ensure `data/` folder has all JSON files

**Data not updating:**
- Verify you pushed the updated JSON files
- Check git status: `git status`
- Force redeploy in Streamlit Cloud if needed

**Slow loading:**
- Large JSON files (>10MB) may slow initial load
- Consider compressing data or paginating

## Cost

**FREE!** Streamlit Community Cloud is free for public apps.

## Support

- Streamlit Docs: https://docs.streamlit.io/
- Community Forum: https://discuss.streamlit.io/
