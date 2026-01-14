# Solana Tax Calculator Web Application

A comprehensive web application for calculating taxes on Solana memecoin trades from Pump.fun and DEX transactions, now with AI-powered tax optimization assistance.

## Features

- 🚀 Beautiful web interface built with Tailwind CSS
- 📊 Calculate capital gains/losses using FIFO or LIFO accounting methods
- 🌍 Support for multiple tax regions (US Federal, California, UK, Germany, India, Australia, Canada, etc.)
- 💰 Real-time SOL price conversion to USD
- 📝 Download detailed tax reports (TXT and CSV formats)
- 🤖 **NEW:** AI Tax Optimization Assistant powered by Claude
- 📈 Wallet analyzer with trading pattern insights
- 🔒 Secure API key management via environment variables

## Setup

1. **Install dependencies:**

```bash
# Make sure you're in your virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Flask dependencies
pip install -r requirements.txt
```

2. **Configure environment variables:**

Create a `.env` file in the project root (copy from `.env.example`):

```bash
# Required: Helius API Key (get one for free at https://www.helius.dev/)
HELIUS_API_KEY=your-helius-api-key-here

# Optional: Anthropic API Key for AI Tax Assistant (get at https://console.anthropic.com/)
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# Optional: Server Port (defaults to 5001)
PORT=5001
```

**IMPORTANT SECURITY NOTE:** Never commit your `.env` file to version control. The `.env` file is already in `.gitignore`.

3. **Run the Flask server:**

```bash
python app.py
```

The server will start on `http://localhost:5001` (port 5001 is used to avoid conflict with macOS AirPlay on port 5000)

4. **Open your browser:**

Navigate to `http://localhost:5001` to access the web interface.

## Usage

### Tax Calculator

1. Navigate to `/tax-calculator`
2. Enter your Solana wallet address
3. Select your accounting method (FIFO or LIFO)
4. Choose your tax region (affects tax rates)
5. Set transaction limit (100 to 10,000 transactions)
6. Click "Calculate Taxes"
7. View results, download reports (TXT or CSV)
8. **NEW:** Click the AI Assistant button (🤖) to get tax optimization advice

### AI Tax Assistant Features

Once your tax calculation is complete, the AI assistant can help you:

- **Tax-Loss Harvesting:** Identify opportunities to offset gains with losses
- **Holding Period Optimization:** Understand short-term vs long-term capital gains impact
- **What-If Scenarios:** "What if I sell 50% of my holdings today?"
- **FIFO vs LIFO Comparison:** Determine which accounting method is better for you
- **General Tax Questions:** Ask about crypto tax rules in your jurisdiction

Example questions to ask the AI:
- "How can I reduce my tax liability?"
- "Should I sell now or wait for long-term capital gains?"
- "What are my biggest tax-loss harvesting opportunities?"
- "Explain my short-term vs long-term gains ratio"

### Wallet Analyzer

1. Navigate to `/wallet-analyzer`
2. Enter your Solana wallet address
3. Select time period to analyze
4. View trading patterns, win rate, top performers, and more

## API Endpoints

### `POST /api/calculate-taxes`

Calculate taxes for a wallet.

**Request Body:**
```json
{
  "walletAddress": "85YnQdx9FhV3tzTeMc2ShyLucV4XXomvbu5WQnn38sEi",
  "apiKey": "your-helius-api-key",
  "accountingMethod": "FIFO",
  "timePeriod": "30"
}
```

**Response:**
```json
{
  "wallet": "...",
  "accounting_method": "FIFO",
  "generated": "2026-01-09 16:20:28",
  "summary": {
    "total_proceeds": 29520.38,
    "total_cost": 23085.76,
    "net_gain": 6434.62,
    "taxable_sales": 773
  },
  "tokens": [...],
  "events": [...],
  "full_report_text": "..."
}
```

### `GET /api/health`

Health check endpoint.

## Command Line Usage

You can also use the calculator directly from the command line:

```bash
python main.py
```

Or with environment variables:

```bash
export HELIUS_API_KEY="your-api-key"
export WALLET_ADDRESS="your-wallet-address"
python main.py
```

## Notes

- The calculation process can take several minutes for active wallets with many transactions
- The calculator supports 100 to 10,000 transactions
- SOL prices are fetched from CoinGecko and cached per day
- Token metadata and prices are fetched from DEX Screener
- Your API keys are stored in environment variables (never hardcoded)
- AI Assistant requires an Anthropic API key (optional feature)

## Export Formats

- **TXT:** Detailed text report with all taxable events
- **CSV:** Spreadsheet-compatible format for Excel, Google Sheets, etc.

## Supported Tax Regions

- 🇺🇸 **United States:** Federal, California, New York, Texas, Florida
- 🇬🇧 **United Kingdom:** 20% CGT with £6,000 annual exemption
- 🇩🇪 **Germany:** Tax-free if held >1 year
- 🇮🇳 **India:** 30% short-term, 20% long-term
- 🇦🇺 **Australia:** 50% CGT discount for >1 year holdings
- 🇨🇦 **Canada:** 50% of gains included in income

## Security Best Practices

1. **Never commit API keys** to version control
2. **Use environment variables** for all sensitive data
3. **Keep your `.env` file private** - it's in `.gitignore` by default
4. **Rotate API keys** if they're ever exposed

## Troubleshooting

### AI Assistant not working
- Check that `ANTHROPIC_API_KEY` is set in your `.env` file
- Verify your API key is valid at [console.anthropic.com](https://console.anthropic.com/)
- Check server logs for error messages

### Calculation errors
- Verify your `HELIUS_API_KEY` is valid
- Check that your wallet address is correct (32-44 characters)
- Reduce transaction limit if timing out
- Check server logs for detailed error messages

### CSV export not working
- Ensure you have completed a tax calculation first
- Check browser console for errors
- Verify Flask server is running

## Contributing

Contributions are welcome! Areas for improvement:
- Additional tax regions
- PDF export functionality
- Real-time price data integration
- Mobile app version
- More AI assistant features

## Disclaimer

⚠️ **IMPORTANT:** This tool is for informational purposes only and does not constitute tax, legal, or financial advice.

- Tax laws vary by jurisdiction and change frequently
- Cryptocurrency tax treatment is complex and evolving
- Always consult with a qualified tax professional for personalized advice
- The AI Assistant provides educational information, not professional tax advice
- Verify all calculations independently before filing taxes

The developers assume no liability for any tax filing errors or penalties resulting from use of this software.

