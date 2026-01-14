# Deployment Guide - Railway

This guide will walk you through deploying Terminal Tools to Railway anonymously.

## Prerequisites

- GitHub account (can be anonymous)
- Railway account (sign up via GitHub - no credit card required for free tier)

## Step 1: Prepare Your Code

### 1.1 Remove Sensitive Data

**CRITICAL: Verify .env is NOT committed**

```bash
# Check if .env is in .gitignore
cat .gitignore | grep .env

# If you accidentally committed .env, remove it from git history:
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env" \
  --prune-empty --tag-name-filter cat -- --all
```

### 1.2 Update Production Settings

Your app is already configured for Railway with:
- `PORT` environment variable support (Railway sets this automatically)
- `host='0.0.0.0'` for external access
- SQLite database (will work on Railway)

## Step 2: Create Anonymous GitHub Repository

### 2.1 Create New GitHub Account (Optional for Anonymity)

1. Go to https://github.com
2. Sign up with temporary/anonymous email:
   - Use ProtonMail, Tutanota, or Guerrilla Mail
   - Username: something generic like `crypto-tools-dev`
3. Enable 2FA with authenticator app (no phone needed)

### 2.2 Push Your Code

```bash
# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit"

# Create new repository on GitHub (via web interface)
# Then push:
git remote add origin https://github.com/YOUR-ANONYMOUS-USERNAME/terminal-tools.git
git branch -M main
git push -u origin main
```

## Step 3: Deploy to Railway

### 3.1 Sign Up for Railway

1. Go to https://railway.app
2. Click "Login" → "Login with GitHub"
3. Authorize Railway to access your GitHub account
4. **Free Tier**: $5 credit/month (no credit card required)

### 3.2 Create New Project

1. Click "New Project"
2. Select "Deploy from GitHub repo"
3. Choose your repository: `YOUR-USERNAME/terminal-tools`
4. Railway will auto-detect it's a Python app

### 3.3 Configure Environment Variables

**IMPORTANT: Set these in Railway dashboard**

1. Go to your project → Click on the service
2. Go to "Variables" tab
3. Add these variables:

```
HELIUS_API_KEY=your-helius-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here
PORT=5001
```

**Note:** Never commit API keys to GitHub. Railway encrypts environment variables.

### 3.4 Deploy

Railway will automatically:
1. Detect Python via `requirements.txt`
2. Install dependencies
3. Run `python app.py` (configured in `Procfile`)
4. Expose your app on a public URL

Your app will be live at: `https://YOUR-APP-NAME.up.railway.app`

## Step 4: Verify Deployment

### 4.1 Check Deployment Logs

1. In Railway dashboard, click "Deployments"
2. View logs to ensure no errors
3. Look for:
   ```
   🚀 Starting Terminal Tools server on http://0.0.0.0:5001
   📍 Landing page: http://0.0.0.0:5001/
   💰 Tax Calculator: http://0.0.0.0:5001/tax-calculator
   🔍 Wallet Analyzer: http://0.0.0.0:5001/wallet-analyzer
   💬 Community Forum: http://0.0.0.0:5001/forum
   🤖 AI Tax Assistant: ENABLED
   ```

### 4.2 Test Your App

Visit your Railway URL and test:
- [ ] Landing page loads
- [ ] Tax Calculator works
- [ ] Wallet Analyzer works
- [ ] Forum works (create a post with Phantom wallet)
- [ ] AI Assistant responds

## Step 5: Custom Domain (Optional)

### 5.1 Railway Subdomain

Free option: `https://your-app.up.railway.app`

### 5.2 Custom Domain with Privacy

1. Buy domain from Namecheap/Njalla with:
   - WHOIS privacy enabled
   - Bitcoin payment (for extra anonymity)

2. In Railway:
   - Go to Settings → Domains
   - Add custom domain
   - Update DNS records as instructed

## Database Considerations

### Current Setup: SQLite

- **Pros**: Simple, no additional cost
- **Cons**: Data resets on redeployment, not ideal for production

### Upgrade to PostgreSQL (Recommended for Production)

Railway offers free PostgreSQL:

1. In Railway project, click "New"
2. Select "Database" → "PostgreSQL"
3. Railway will provide connection URL

Then update your code to use PostgreSQL instead of SQLite:

```bash
pip install psycopg2-binary
```

Update `forum_db.py` to use PostgreSQL connection string from environment variable.

## Security Checklist

Before going live:

- [ ] `.env` is in `.gitignore`
- [ ] No API keys in code
- [ ] Environment variables set in Railway
- [ ] HTTPS enabled (automatic on Railway)
- [ ] Forum word blacklist is active
- [ ] Rate limiting enabled (optional - add Flask-Limiter)

## Monitoring

### Railway Dashboard

- View real-time logs
- Monitor resource usage
- Check deployment status

### Usage Limits (Free Tier)

- $5 credit/month
- ~500 hours of runtime
- 1GB RAM
- 1 vCPU

## Updating Your App

### Push Updates

```bash
# Make changes
git add .
git commit -m "Update feature X"
git push origin main
```

Railway will automatically redeploy on push.

## Troubleshooting

### App Won't Start

Check logs for:
- Missing environment variables
- Python dependency errors
- Port binding issues

### Forum Posts Not Persisting

- SQLite database resets on redeploy
- Upgrade to PostgreSQL for persistence

### API Rate Limits

- Helius free tier: 100 requests/second
- Anthropic: $5 minimum credit purchase

## Cost Estimate

**Free Tier (Railway)**
- $5 credit/month
- Sufficient for low-medium traffic

**Paid Tier (If Needed)**
- ~$0.000463/GB-hour for memory
- ~$0.000231/vCPU-hour

**Example**: Medium traffic site ~$10-20/month

## Going Full Anonymous

1. **Payment**: Use prepaid debit card or crypto
2. **Email**: ProtonMail with VPN
3. **GitHub**: Anonymous account, no personal info
4. **Domain**: Njalla (accepts crypto, max privacy)
5. **VPN**: Use when deploying

## Support

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- GitHub Issues: (create in your repo)

---

**You're Done!** 🎉

Your app is now live at: `https://your-app.up.railway.app`

Share the link and start building your community!
