# Railway Deployment Checklist

Quick reference for deploying to Railway anonymously.

## Pre-Deployment

- [ ] Verify `.env` is in `.gitignore`
- [ ] Test app locally: `./start.sh`
- [ ] All features working:
  - [ ] Tax Calculator
  - [ ] Wallet Analyzer
  - [ ] Forum (posts & replies)
  - [ ] AI Assistant

## GitHub Setup

- [ ] Create anonymous GitHub account (optional)
  - Email: Use ProtonMail/Tutanota
  - Username: Generic (e.g., `crypto-dev-tools`)
  - Enable 2FA with authenticator app

- [ ] Create new repository
  ```bash
  # On GitHub: Create new repo (private or public)
  # Then locally:
  git init
  git add .
  git commit -m "Initial commit"
  git remote add origin https://github.com/YOUR-USERNAME/your-repo.git
  git push -u origin main
  ```

## Railway Setup

### 1. Create Account
- [ ] Go to https://railway.app
- [ ] Login with GitHub
- [ ] Free tier: $5 credit/month (no card needed)

### 2. Deploy
- [ ] Click "New Project"
- [ ] Select "Deploy from GitHub repo"
- [ ] Choose your repository
- [ ] Wait for initial deploy

### 3. Environment Variables
Go to Variables tab and add:

```
HELIUS_API_KEY=your-helius-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here
PORT=5001
```

**Replace with your actual API keys!**

### 4. Verify Deployment
- [ ] Check deployment logs (should show "Starting Terminal Tools")
- [ ] Visit your Railway URL: `https://your-app.up.railway.app`
- [ ] Test all features

## Post-Deployment

- [ ] Share your URL
- [ ] Monitor usage in Railway dashboard
- [ ] Watch free tier credit usage

## Quick Commands

### Update App
```bash
git add .
git commit -m "Your update message"
git push origin main
# Railway auto-deploys
```

### View Logs
Go to Railway dashboard → Deployments → View logs

### Rollback
Railway dashboard → Deployments → Click previous deployment → Redeploy

## Notes

- **SQLite caveat**: Forum posts reset on redeploy. For production, upgrade to PostgreSQL (free on Railway).
- **Free tier**: ~500 hours/month runtime, sufficient for most use cases
- **Custom domain**: Optional, configure in Railway Settings → Domains

## Estimated Time

- GitHub setup: 5 minutes
- Railway deployment: 10 minutes
- Testing: 5 minutes

**Total: ~20 minutes** ⚡

---

**Next Steps After Deployment:**
1. Test thoroughly
2. Share your link
3. Monitor usage
4. (Optional) Add custom domain
5. (Optional) Upgrade to PostgreSQL for forum persistence
