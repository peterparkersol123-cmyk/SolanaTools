from flask import Flask, request, jsonify, send_file, Response, stream_with_context
from flask_cors import CORS
import os
import json
import queue
import threading
import logging
from main import SolanaMemecoinTaxCalculator, TaxRegion
from datetime import datetime, timedelta
from dotenv import load_dotenv
from forum_db import ForumDatabase

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend-backend communication

# Initialize forum database
forum_db = ForumDatabase()

# Serve landing page as the root
@app.route('/')
def landing():
    return send_file('landing.html')

# Serve the tax calculator app
@app.route('/tax-calculator')
def tax_calculator():
    return send_file('index.html')

# Serve the wallet analyzer app
@app.route('/wallet-analyzer')
def wallet_analyzer():
    return send_file('wallet-analyzer.html')

# Serve the forum app
@app.route('/forum')
def forum():
    return send_file('forum.html')

# Alternative route (for backwards compatibility if you had bookmarks)
@app.route('/index.html')
def index_redirect():
    return send_file('index.html')

@app.route('/api/calculate-taxes', methods=['POST'])
def calculate_taxes():
    """
    API endpoint to calculate taxes for a Solana wallet (streaming version)
    Uses Server-Sent Events (SSE) to stream progress updates
    Expects JSON with:
    - walletAddress: str
    - accountingMethod: str (FIFO or LIFO)
    - maxTransactions: int (100, 500, 1000, 2500, 5000, or 10000)
    - taxRegion: str (us_federal, us_california, uk, etc.)
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        wallet_address = data.get('walletAddress', '').strip()
        accounting_method = data.get('accountingMethod', 'FIFO').strip().upper()
        max_transactions = data.get('maxTransactions', '1000').strip()
        tax_region_str = data.get('taxRegion', 'us_federal').strip()

        # Get API key from environment variable or request
        api_key = os.environ.get('HELIUS_API_KEY') or data.get('apiKey', '').strip()

        if not api_key:
            return jsonify({'error': 'API key is required. Please provide a Helius API key or set HELIUS_API_KEY environment variable.'}), 400
        
        if not wallet_address or len(wallet_address) < 32:
            return jsonify({'error': 'Invalid wallet address'}), 400
        
        # Convert max transactions to integer
        try:
            max_transactions = int(max_transactions)
            if max_transactions < 1 or max_transactions > 10000:
                return jsonify({'error': 'Transaction limit must be between 1 and 10,000'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid transaction limit'}), 400
        
        # Map tax region string to TaxRegion enum
        tax_region_map = {
            'us_federal': TaxRegion.US_FEDERAL,
            'us_california': TaxRegion.US_CALIFORNIA,
            'us_new_york': TaxRegion.US_NEW_YORK,
            'us_texas': TaxRegion.US_TEXAS,
            'us_florida': TaxRegion.US_FLORIDA,
            'uk': TaxRegion.UK,
            'india': TaxRegion.INDIA,
            'germany': TaxRegion.GERMANY,
            'australia': TaxRegion.AUSTRALIA,
            'canada': TaxRegion.CANADA,
        }
        
        tax_region = tax_region_map.get(tax_region_str, TaxRegion.US_FEDERAL)
        
        def generate():
            """Generator function that yields SSE events"""
            try:
                # Create a queue to collect updates from the callback
                update_queue = queue.Queue()
                incremental_events = []
                
                # Create calculator instance with tax region
                calc = SolanaMemecoinTaxCalculator(
                    wallet_address=wallet_address,
                    helius_api_key=api_key,
                    accounting_method=accounting_method,
                    max_transactions=max_transactions,
                    tax_region=tax_region
                )
                
                def progress_callback(update):
                    """Callback function that puts updates in the queue"""
                    update_queue.put(update)
                
                # Start calculation in a separate thread to allow streaming
                calculation_done = threading.Event()
                calculation_error = [None]
                
                def run_calculation():
                    try:
                        result = calc.calculate_taxes_from_wallet(progress_callback=progress_callback)
                        if result is None:
                            update_queue.put({'type': 'error', 'message': 'No transactions found'})
                        else:
                            # Put final report in queue
                            report = calc.generate_json_report()
                            update_queue.put({'type': 'complete', 'report': report})
                    except Exception as e:
                        calculation_error[0] = e
                        update_queue.put({'type': 'error', 'message': str(e)})
                    finally:
                        calculation_done.set()
                
                # Start calculation thread
                calc_thread = threading.Thread(target=run_calculation, daemon=True)
                calc_thread.start()
                
                # Track gains by token mint for progressive updates
                gains_by_mint = {}
                
                # Stream updates as they come in
                while not calculation_done.is_set() or not update_queue.empty():
                    try:
                        # Get update with timeout to allow checking if calculation is done
                        try:
                            update = update_queue.get(timeout=0.1)
                        except queue.Empty:
                            # Yield a keep-alive comment to prevent connection timeout
                            yield ": keep-alive\n\n"
                            continue
                        
                        update_type = update.get('type')
                        
                        if update_type == 'status':
                            yield "data: " + json.dumps({'type': 'status', 'message': update['message']}) + "\n\n"
                        elif update_type == 'fetch_progress':
                            yield "data: " + json.dumps({'type': 'fetch_progress', 'message': update['message'], 'data': update.get('data', {})}) + "\n\n"
                        elif update_type == 'progress':
                            yield "data: " + json.dumps({'type': 'progress', 'message': update['message'], 'data': update.get('data', {})}) + "\n\n"
                        elif update_type == 'event':
                            # Send new taxable event
                            event_data = update.get('data', {}).get('event')
                            if event_data:
                                incremental_events.append(event_data)
                                
                                # Update gains by token mint
                                token_mint = event_data.get('token_mint', '')
                                if token_mint:
                                    if token_mint not in gains_by_mint:
                                        gains_by_mint[token_mint] = 0.0
                                    gains_by_mint[token_mint] += event_data.get('gain', 0)
                                    
                                    # Get token metadata from the update (provided by main.py)
                                    token_metadata = update.get('data', {}).get('token_metadata')

                                    # Send token update if we have metadata
                                    if token_metadata:
                                        token_update_data = {
                                            'type': 'token_update',
                                            'token': {
                                                'symbol': token_metadata.get('symbol', event_data.get('token', '')),
                                                'name': token_metadata.get('name', event_data.get('token', '')),
                                                'logoURI': token_metadata.get('logoURI', ''),
                                                'mint': token_mint,
                                                'gain': round(gains_by_mint[token_mint], 2)
                                            }
                                        }
                                        yield "data: " + json.dumps(token_update_data) + "\n\n"
                                    else:
                                        # If no metadata yet, still send update with basic info
                                        # Metadata will be fetched and updated later
                                        token_update_data = {
                                            'type': 'token_update',
                                            'token': {
                                                'symbol': event_data.get('token', ''),
                                                'name': event_data.get('token', ''),
                                                'logoURI': '',
                                                'mint': token_mint,
                                                'gain': round(gains_by_mint[token_mint], 2)
                                            }
                                        }
                                        yield "data: " + json.dumps(token_update_data) + "\n\n"
                                
                                # Send partial summary update
                                total_gains = sum(e['gain'] for e in incremental_events)
                                total_proceeds = sum(e['proceeds'] for e in incremental_events)
                                total_cost = sum(e['cost'] for e in incremental_events)
                                
                                event_update_data = {
                                    'type': 'event',
                                    'event': event_data,
                                    'partial_summary': {
                                        'total_proceeds': round(total_proceeds, 2),
                                        'total_cost': round(total_cost, 2),
                                        'net_gain': round(total_gains, 2),
                                        'taxable_sales': len(incremental_events)
                                    }
                                }
                                yield "data: " + json.dumps(event_update_data) + "\n\n"
                        elif update_type == 'error':
                            yield "data: " + json.dumps({'type': 'error', 'message': update['message']}) + "\n\n"
                        elif update_type == 'complete':
                            # Generate final report message
                            yield "data: " + json.dumps({'type': 'status', 'message': 'Generating final report...'}) + "\n\n"
                            yield "data: " + json.dumps({'type': 'complete', 'report': update['report']}) + "\n\n"
                            break
                            
                    except Exception as e:
                        error_msg = "Error processing update: " + str(e)
                        yield "data: " + json.dumps({'type': 'error', 'message': error_msg}) + "\n\n"

                # Check if there was an error in calculation
                if calculation_error[0]:
                    yield "data: " + json.dumps({'type': 'error', 'message': str(calculation_error[0])}) + "\n\n"

            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                logger.error(f"Error calculating taxes: {error_details}")
                yield "data: " + json.dumps({'type': 'error', 'message': str(e)}) + "\n\n"
        
        # Return streaming response with SSE headers
        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'  # Disable buffering in nginx
            }
        )
        
    except Exception as e:
        # Log error for debugging
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error in calculate_taxes endpoint: {error_details}")
        
        return jsonify({
            'error': str(e),
            'message': 'An error occurred while calculating taxes. Please check your inputs and try again.'
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/api/export-csv', methods=['POST'])
def export_csv():
    """
    Export tax report to CSV format
    Expects JSON with:
    - reportData: dict (the complete tax report)
    """
    try:
        import csv
        from io import StringIO

        data = request.get_json()
        report_data = data.get('reportData', {})

        if not report_data:
            return jsonify({'error': 'No report data provided'}), 400

        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)

        # Summary section
        writer.writerow(['TAX REPORT SUMMARY'])
        writer.writerow(['Wallet', report_data.get('wallet', '')])
        writer.writerow(['Accounting Method', report_data.get('accounting_method', '')])
        writer.writerow(['Tax Region', report_data.get('tax_region', '')])
        writer.writerow(['Generated', report_data.get('generated', '')])
        writer.writerow([])

        summary = report_data.get('summary', {})
        writer.writerow(['SUMMARY'])
        writer.writerow(['Total Proceeds', f"{summary.get('total_proceeds', 0):.2f}"])
        writer.writerow(['Total Cost Basis', f"{summary.get('total_cost', 0):.2f}"])
        writer.writerow(['Net Gain/Loss', f"{summary.get('net_gain', 0):.2f}"])
        writer.writerow(['Total Tax Liability', f"{summary.get('total_tax_liability', 0):.2f}"])
        writer.writerow(['Taxable Sales', summary.get('taxable_sales', 0)])
        writer.writerow([])

        # Taxable events
        writer.writerow([])
        writer.writerow(['TAXABLE EVENTS'])
        writer.writerow(['Date', 'Token', 'Amount', 'Proceeds', 'Cost Basis', 'Gain/Loss', 'Holding Period (days)', 'Term Type', 'Tax Owed'])

        events = report_data.get('events', [])
        for event in events:
            # Parse date if it's a datetime object
            date_str = event.get('date', '')
            if hasattr(date_str, 'strftime'):
                date_str = date_str.strftime('%Y-%m-%d')
            elif isinstance(date_str, str):
                date_str = date_str.split()[0] if ' ' in date_str else date_str

            writer.writerow([
                date_str,
                event.get('token', ''),
                f"{event.get('amount', 0):.4f}",
                f"{event.get('proceeds', 0):.2f}",
                f"{event.get('cost', 0):.2f}",
                f"{event.get('gain', 0):.2f}",
                event.get('holding_days', 0),
                event.get('term_type', ''),
                f"{event.get('tax', 0):.2f}"
            ])

        writer.writerow([])

        # Token summary
        writer.writerow([])
        writer.writerow(['GAINS/LOSSES BY TOKEN'])
        writer.writerow(['Token Name', 'Symbol', 'Total Gain/Loss'])

        tokens = report_data.get('tokens', [])
        for token in tokens:
            writer.writerow([
                token.get('name', ''),
                token.get('symbol', ''),
                f"{token.get('gain', 0):.2f}"
            ])

        # Get CSV content
        csv_content = output.getvalue()
        output.close()

        # Create response
        response = Response(
            csv_content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=tax_report_{report_data.get("wallet", "")[:8]}_{report_data.get("accounting_method", "FIFO")}.csv'
            }
        )

        return response

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error exporting CSV: {error_details}")

        return jsonify({
            'error': str(e),
            'message': 'An error occurred while exporting to CSV.'
        }), 500

@app.route('/api/analyze-wallet', methods=['POST'])
def analyze_wallet():
    """
    API endpoint to analyze a Solana wallet's trading patterns
    Expects JSON with:
    - walletAddress: str
    - maxTransactions: int
    - timePeriod: str (all, 30, 90, 180)
    """
    try:
        from wallet_analyzer import WalletAnalyzer
        
        data = request.get_json()
        
        # Validate required fields
        wallet_address = data.get('walletAddress', '').strip()
        time_period_hours = data.get('timePeriod', 24)  # Default to 24 hours

        # Get API key from environment variable or request
        api_key = os.environ.get('HELIUS_API_KEY') or data.get('apiKey', '').strip()

        if not api_key:
            return jsonify({'error': 'API key is required. Please provide a Helius API key or set HELIUS_API_KEY environment variable.'}), 400
        
        if not wallet_address or len(wallet_address) < 32:
            return jsonify({'error': 'Invalid wallet address'}), 400
        
        # Use existing calculator infrastructure to fetch transactions
        calc = SolanaMemecoinTaxCalculator(
            wallet_address=wallet_address,
            helius_api_key=api_key,
            accounting_method='FIFO',
            max_transactions=1000,  # Fixed at 1000 for consistency
            tax_region=TaxRegion.US_FEDERAL
        )
        
        # Fetch and process transactions using the calculator's method
        result = calc.calculate_taxes_from_wallet()
        
        if result is None or not calc.taxable_events:
            return jsonify({'error': 'No transactions found for this wallet'}), 404
        
        # Analyze wallet using processed transactions
        analyzer = WalletAnalyzer(wallet_address, calc, time_period_hours)
        results = analyzer.analyze()
        
        return jsonify(results)
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error in analyze_wallet endpoint: {error_details}")
        
        return jsonify({
            'error': str(e),
            'message': 'An error occurred while analyzing the wallet. Please check your inputs and try again.'
        }), 500

@app.route('/api/ai-chat', methods=['POST'])
def ai_chat():
    """
    AI Tax Assistant chat endpoint
    Expects JSON with:
    - message: str (user's question)
    - taxData: dict (current tax calculation data)
    - conversationHistory: list (optional, for context)
    """
    try:
        from tax_assistant import TaxAssistant

        data = request.get_json()
        user_message = data.get('message', '').strip()
        tax_data = data.get('taxData', {})

        if not user_message:
            return jsonify({'error': 'Message is required'}), 400

        # Check if Anthropic API key is available
        if not os.environ.get('ANTHROPIC_API_KEY'):
            return jsonify({
                'error': 'AI Assistant not configured. Please set ANTHROPIC_API_KEY environment variable.',
                'isConfigured': False
            }), 400

        # Create assistant instance
        assistant = TaxAssistant()

        # Restore conversation history if provided
        conversation_history = data.get('conversationHistory', [])
        if conversation_history:
            assistant.conversation_history = conversation_history

        # Get AI response
        response_text = assistant.chat(user_message, tax_data)

        return jsonify({
            'response': response_text,
            'conversationHistory': assistant.conversation_history,
            'isConfigured': True
        })

    except ImportError:
        return jsonify({
            'error': 'Tax assistant module not available. Please install required dependencies.',
            'isConfigured': False
        }), 500
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error in AI chat endpoint: {error_details}")

        return jsonify({
            'error': str(e),
            'message': 'An error occurred while processing your message. Please try again.'
        }), 500

@app.route('/api/ai-suggestions', methods=['POST'])
def ai_suggestions():
    """
    Get proactive AI tax optimization suggestions
    Expects JSON with:
    - taxData: dict (current tax calculation data)
    """
    try:
        from tax_assistant import TaxAssistant

        data = request.get_json()
        tax_data = data.get('taxData', {})

        # Check if Anthropic API key is available
        if not os.environ.get('ANTHROPIC_API_KEY'):
            return jsonify({
                'suggestions': [],
                'isConfigured': False
            })

        # Create assistant instance
        assistant = TaxAssistant()

        # Get suggestions
        suggestions = assistant.get_suggestions(tax_data)

        return jsonify({
            'suggestions': suggestions,
            'isConfigured': True
        })

    except ImportError:
        return jsonify({
            'suggestions': [],
            'isConfigured': False
        })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error in AI suggestions endpoint: {error_details}")

        return jsonify({
            'suggestions': [],
            'error': str(e)
        }), 500

# Forum API endpoints
@app.route('/api/forum/posts', methods=['GET'])
def get_forum_posts():
    """Get all forum posts with replies"""
    try:
        posts = forum_db.get_all_posts()
        return jsonify({'posts': posts})
    except Exception as e:
        logger.error(f"Error getting forum posts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/forum/posts', methods=['POST'])
def create_forum_post():
    """Create a new forum post"""
    try:
        data = request.json
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        author = data.get('author', '').strip()

        if not title or not content or not author:
            return jsonify({'error': 'Title, content, and author are required'}), 400

        post = forum_db.create_post(title, content, author)
        return jsonify({'post': post}), 201
    except Exception as e:
        logger.error(f"Error creating forum post: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/forum/posts/<int:post_id>/replies', methods=['POST'])
def create_forum_reply(post_id):
    """Create a reply to a post"""
    try:
        data = request.json
        content = data.get('content', '').strip()
        author = data.get('author', '').strip()

        if not content or not author:
            return jsonify({'error': 'Content and author are required'}), 400

        reply = forum_db.create_reply(post_id, content, author)
        return jsonify({'reply': reply}), 201
    except Exception as e:
        logger.error(f"Error creating reply: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Run Flask app
    # Use port 5001 by default to avoid conflict with macOS AirPlay (port 5000)
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"🚀 Starting Terminal Tools server on http://localhost:{port}")
    logger.info(f"📍 Landing page: http://localhost:{port}/")
    logger.info(f"💰 Tax Calculator: http://localhost:{port}/tax-calculator")
    logger.info(f"🔍 Wallet Analyzer: http://localhost:{port}/wallet-analyzer")
    logger.info(f"💬 Community Forum: http://localhost:{port}/forum")

    # Check if AI Assistant is configured
    if os.environ.get('ANTHROPIC_API_KEY'):
        logger.info(f"🤖 AI Tax Assistant: ENABLED")
    else:
        logger.warning(f"🤖 AI Tax Assistant: DISABLED (set ANTHROPIC_API_KEY to enable)")

    app.run(host='0.0.0.0', port=port, debug=True)