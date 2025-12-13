"""
BingX Trading Bot - FastAPI Server
Docker Compatible Version
"""
import asyncio
import time
import json
import hashlib
import hmac
import aiohttp
from fastapi import FastAPI, Request, Response
import os

# ========== CONFIGURAÇÃO ==========
API_KEY = os.getenv("BINGX_API_KEY")
SECRET_KEY = os.getenv("BINGX_SECRET_KEY")
SYMBOL = "ETH-USDT"

print(f"🔧 Config loaded:")
print(f"   Symbol: {SYMBOL}")
print(f"   API Key: {'✅ SET' if API_KEY else '❌ MISSING'}")
print(f"   Secret Key: {'✅ SET' if SECRET_KEY else '❌ MISSING'}")

# ========== HTTP CLIENT ==========
_session = None

async def get_session():
    """Get HTTP session"""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session

def generate_signature(params: dict) -> str:
    """Generate HMAC signature for BingX API"""
    query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
    return hmac.new(
        SECRET_KEY.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

async def bingx_request(method: str, endpoint: str, params=None, signed=False):
    """Make request to BingX API"""
    try:
        session = await get_session()
        url = f"https://open-api.bingx.com{endpoint}"
        
        if params is None:
            params = {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = generate_signature(params)
        
        headers = {"X-BX-APIKEY": API_KEY} if signed else {}
        
        print(f"[API] {method} {endpoint}")
        
        async with session.request(
            method=method,
            url=url,
            params=params if method == "GET" else None,
            json=params if method == "POST" else None,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('code') == 0:
                    return data.get('data')
                else:
                    print(f"[API ERROR] Code: {data.get('code')}, Msg: {data.get('msg')}")
                    return None
            else:
                print(f"[API ERROR] HTTP {response.status}")
                return None
                
    except Exception as e:
        print(f"[API EXCEPTION] {str(e)}")
        return None

# ========== TRADING FUNCTIONS ==========
async def get_current_price():
    """Get current ETH-USDT price"""
    data = await bingx_request("GET", "/openApi/swap/v2/quote/ticker", {"symbol": SYMBOL})
    
    if data:
        if isinstance(data, list) and len(data) > 0:
            price = float(data[0].get('lastPrice', 0))
        elif isinstance(data, dict):
            price = float(data.get('lastPrice', 0))
        else:
            price = 0.0
        
        print(f"[PRICE] ETH-USDT: ${price}")
        return price
    
    return 0.0

async def get_account_balance():
    """Get account balance"""
    data = await bingx_request("GET", "/openApi/swap/v2/user/balance", signed=True)
    
    if data and 'balance' in data:
        for asset in data['balance']:
            if asset.get('asset') == 'USDT':
                balance = float(asset.get('balance', 0))
                print(f"[BALANCE] USDT: ${balance}")
                return balance
    
    return 0.0

async def get_position():
    """Get current position"""
    data = await bingx_request("GET", "/openApi/swap/v2/user/positions", signed=True)
    
    if data:
        if isinstance(data, list):
            for pos in data:
                if pos.get('symbol') == SYMBOL:
                    print(f"[POSITION] Found: {pos.get('positionAmt', 0)} ETH")
                    return pos
        elif isinstance(data, dict) and data.get('symbol') == SYMBOL:
            print(f"[POSITION] Found: {data.get('positionAmt', 0)} ETH")
            return data
    
    print("[POSITION] No position found")
    return None

async def place_market_order(side: str, quantity: float):
    """Place market order"""
    params = {
        "symbol": SYMBOL,
        "side": side.upper(),
        "type": "MARKET",
        "quantity": round(quantity, 4),
        "positionSide": "LONG" if side.upper() == "BUY" else "SHORT"
    }
    
    print(f"[ORDER] {side.upper()} {quantity} ETH")
    
    result = await bingx_request("POST", "/openApi/swap/v2/trade/order", params, signed=True)
    
    if result and 'orderId' in result:
        print(f"[ORDER SUCCESS] ID: {result['orderId']}")
        return True
    else:
        print("[ORDER FAILED]")
        return False

# ========== SIGNAL PROCESSING ==========
async def process_signal(action: str):
    """Process trading signal"""
    print(f"[SIGNAL] Processing: {action}")
    
    if action == "ENTER-LONG":
        return await enter_long()
    elif action == "ENTER-SHORT":
        return await enter_short()
    elif action == "EXIT-LONG":
        return await exit_position("LONG")
    elif action == "EXIT-SHORT":
        return await exit_position("SHORT")
    elif action == "EXIT-ALL":
        return await exit_all_positions()
    else:
        return {"success": False, "error": "Unknown action"}

async def enter_long():
    """Open LONG position"""
    print("[TRADE] Opening LONG position...")
    
    balance = await get_account_balance()
    price = await get_current_price()
    
    print(f"[TRADE DATA] Balance: ${balance}, Price: ${price}")
    
    if balance <= 0 or price <= 0:
        return {"success": False, "error": "Invalid balance or price"}
    
    # 40% of balance
    usd_amount = balance * 0.4
    quantity = round(usd_amount / price, 4)
    
    if quantity <= 0:
        return {"success": False, "error": "Invalid quantity"}
    
    print(f"[TRADE] Buying {quantity} ETH (${usd_amount})")
    
    success = await place_market_order("BUY", quantity)
    return {"success": success}

async def enter_short():
    """Open SHORT position"""
    print("[TRADE] Opening SHORT position...")
    
    balance = await get_account_balance()
    price = await get_current_price()
    
    print(f"[TRADE DATA] Balance: ${balance}, Price: ${price}")
    
    if balance <= 0 or price <= 0:
        return {"success": False, "error": "Invalid balance or price"}
    
    usd_amount = balance * 0.4
    quantity = round(usd_amount / price, 4)
    
    if quantity <= 0:
        return {"success": False, "error": "Invalid quantity"}
    
    print(f"[TRADE] Selling {quantity} ETH (${usd_amount})")
    
    success = await place_market_order("SELL", quantity)
    return {"success": success}

async def exit_position(side: str):
    """Close specific position"""
    print(f"[TRADE] Closing {side} position...")
    
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        return {"success": True, "message": "No position to close"}
    
    current_side = "LONG" if float(position.get('positionAmt', 0)) > 0 else "SHORT"
    
    if (side == "LONG" and current_side == "SHORT") or (side == "SHORT" and current_side == "LONG"):
        return {"success": True, "message": "Position side mismatch"}
    
    quantity = abs(float(position.get('positionAmt', 0)))
    close_side = "SELL" if current_side == "LONG" else "BUY"
    
    print(f"[TRADE] Closing {quantity} ETH ({current_side} → {close_side})")
    
    success = await place_market_order(close_side, quantity)
    return {"success": success}

async def exit_all_positions():
    """Close all positions"""
    print("[TRADE] Closing ALL positions...")
    
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        return {"success": True, "message": "No open positions"}
    
    quantity = abs(float(position.get('positionAmt', 0)))
    side = "SELL" if float(position.get('positionAmt', 0)) > 0 else "BUY"
    
    print(f"[TRADE] Closing all: {quantity} ETH ({side})")
    
    success = await place_market_order(side, quantity)
    return {"success": success}

# ========== FASTAPI APP ==========
app = FastAPI(title="BingX Trading Bot", version="1.0")

_processed_signals = set()

@app.on_event("startup")
async def startup():
    """Server startup"""
    print("\n" + "=" * 60)
    print("✅ SERVER STARTED SUCCESSFULLY")
    print("=" * 60)
    print(f"🌐 External URL: https://bingx-ultra-fast-trading-bot.onrender.com")
    print(f"📡 Webhook: POST /webhook")
    print(f"🏥 Health: GET /status")
    print("=" * 60)
    print("\n📢 WAITING FOR TRADINGVIEW SIGNALS...\n")

@app.on_event("shutdown")
async def shutdown():
    """Server shutdown"""
    print("\n👋 Server shutting down...")
    global _session
    if _session:
        await _session.close()

# ========== ROUTES ==========
@app.post("/webhook")
async def webhook(request: Request):
    """TradingView webhook endpoint"""
    print("\n" + "=" * 50)
    print("📨 WEBHOOK RECEIVED")
    
    try:
        # Read message
        body = await request.body()
        message = body.decode('utf-8').strip()
        
        print(f"📝 Message: {message}")
        
        # Validate format
        if not message or len(message) < 10:
            return Response(
                content=json.dumps({"error": "Empty or invalid message"}),
                media_type="application/json",
                status_code=400
            )
        
        # Extract action
        action = None
        if "ENTER-LONG" in message:
            action = "ENTER-LONG"
        elif "EXIT-LONG" in message:
            action = "EXIT-LONG"
        elif "ENTER-SHORT" in message:
            action = "ENTER-SHORT"
        elif "EXIT-SHORT" in message:
            action = "EXIT-SHORT"
        elif "EXIT-ALL" in message:
            action = "EXIT-ALL"
        
        if not action:
            return Response(
                content=json.dumps({"error": "Unknown action"}),
                media_type="application/json",
                status_code=400
            )
        
        # Check duplicate (simple hash)
        msg_hash = hash(message)
        if msg_hash in _processed_signals:
            print("⚠️  Duplicate signal, ignoring...")
            return Response(
                content=json.dumps({"status": "duplicate"}),
                media_type="application/json"
            )
        
        _processed_signals.add(msg_hash)
        if len(_processed_signals) > 100:
            _processed_signals.clear()
        
        # Process signal
        result = await process_signal(action)
        
        if result.get("success"):
            print(f"✅ Action '{action}' executed successfully!")
            return Response(
                content=json.dumps({
                    "status": "success",
                    "action": action,
                    "message": "Trade executed"
                }),
                media_type="application/json"
            )
        else:
            print(f"❌ Action '{action}' failed: {result.get('error')}")
            return Response(
                content=json.dumps({
                    "status": "error",
                    "action": action,
                    "error": result.get("error", "Unknown error")
                }),
                media_type="application/json",
                status_code=500
            )
            
    except Exception as e:
        print(f"💥 Webhook error: {str(e)}")
        return Response(
            content=json.dumps({"error": str(e)}),
            media_type="application/json",
            status_code=500
        )

@app.get("/status")
async def status():
    """Health check endpoint for Render/UptimeRobot"""
    try:
        price = await get_current_price()
        return {
            "status": "online",
            "service": "BingX Trading Bot",
            "symbol": SYMBOL,
            "price": price,
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": time.time()
        }

@app.get("/")
async def root():
    """Home page"""
    return {
        "service": "BingX Ultra-Fast Trading Bot",
        "status": "🟢 ONLINE",
        "version": "1.0.0",
        "docker": True,
        "endpoints": {
            "webhook": "POST /webhook - TradingView signals",
            "status": "GET /status - Health check",
            "test": "GET /test - Connection test"
        },
        "instructions": {
            "tradingview": "Webhook URL: https://bingx-ultra-fast-trading-bot.onrender.com/webhook",
            "message": "Use: {{strategy.order.comment}}"
        }
    }

@app.get("/test")
async def test():
    """Connection test endpoint"""
    return {
        "success": True,
        "message": "Bot is running!",
        "docker": True,
        "api_configured": bool(API_KEY and SECRET_KEY),
        "timestamp": time.time()
    }
