# Quick Start Guide

Get up and running with the Solana Tax Calculator in 5 minutes!

## Step 1: Install Dependencies

```bash
# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate     # Windows

# Install requirements
pip install -r requirements.txt
```

## Step 2: Get Your API Keys

### Required: Helius API Key
1. Go to [helius.dev](https://www.helius.dev/)
2. Sign up for a free account
3. Create a new API key
4. Copy the API key

### Optional: Anthropic API Key (for AI Assistant)
1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Sign up and add credits ($5 minimum)
3. Create a new API key
4. Copy the API key

## Step 3: Configure Environment Variables

Create a `.env` file in the project root:

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your keys
nano .env  # or use any text editor
```

Your `.env` should look like:
```
HELIUS_API_KEY=your-actual-helius-key-here
ANTHROPIC_API_KEY=your-actual-anthropic-key-here
```

## Step 4: Run the Server

```bash
python app.py
```

You should see:
```
🚀 Starting Terminal Tools server on http://localhost:5001
📍 Landing page: http://localhost:5001/
💰 Tax Calculator: http://localhost:5001/tax-calculator
🔍 Wallet Analyzer: http://localhost:5001/wallet-analyzer
🤖 AI Tax Assistant: ENABLED
```

## Step 5: Calculate Your Taxes

1. Open http://localhost:5001/tax-calculator in your browser
2. Enter your Solana wallet address
3. Select your tax region and accounting method
4. Click "Calculate Taxes"
5. Wait for results (may take 1-2 minutes)
6. Click the 🤖 button to chat with the AI Tax Assistant!

## Common Issues

### "AI Assistant not configured"
- Make sure you added `ANTHROPIC_API_KEY` to your `.env` file
- Restart the server after adding the key

### "Invalid API key"
- Double-check your Helius API key is correct
- Make sure there are no extra spaces in your `.env` file

### Port 5001 already in use
- Change the port: `PORT=8080 python app.py`
- Or kill the process using port 5001

## Next Steps

- Try the Wallet Analyzer at `/wallet-analyzer`
- Export your report as CSV for your accountant
- Ask the AI Assistant about tax optimization strategies
- Read the full [README.md](README.md) for advanced features

## Support

- Issues: https://github.com/your-repo/issues (if you have a repo)
- Helius Support: https://docs.helius.dev/
- Anthropic Support: https://docs.anthropic.com/

Happy tax calculating! 📊💰
