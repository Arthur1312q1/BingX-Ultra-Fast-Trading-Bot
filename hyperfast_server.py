"""
Servidor HTTP corrigido para API BingX
"""
import asyncio
import time
import json
import hashlib
import hmac
import aiohttp
from fastapi import FastAPI, Request, APIRouter, Response
import os
import re

# ========== CONFIGURAÇÃO ==========
API_KEY = os.getenv("BINGX_API_KEY")
SECRET_KEY = os.getenv("BINGX_SECRET_KEY")
SYMBOL = "ETH-USDT"

print(f"🔧 Configuração carregada:")
print(f"   Símbolo: {SYMBOL}")
print(f"   API Key: {'✅' if API_KEY else '❌'}")
print(f"   Secret: {'✅' if SECRET_KEY else '❌'}")

# ========== CLIENTE HTTP ==========
_session = None

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session

def generate_signature(params: dict) -> str:
    query = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
    return hmac.new(
        SECRET_KEY.encode('utf-8'),
        query.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

async def bingx_request(method: str, endpoint: str, params=None, signed=False):
    """Requisição à API BingX corrigida"""
    try:
        session = await get_session()
        url = f"https://open-api.bingx.com{endpoint}"
        
        if params is None:
            params = {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = generate_signature(params)
        
        headers = {}
        if signed:
            headers["X-BX-APIKEY"] = API_KEY
        
        print(f"📡 Request: {method} {endpoint}")
        
        if method.upper() == "GET":
            async with session.get(url, params=params, headers=headers) as response:
                text = await response.text()
                print(f"📥 Response: {response.status} - {text[:200]}")
                
                if response.status == 200:
                    try:
                        data = json.loads(text)
                        if data.get('code') == 0:
                            return data.get('data')
                        else:
                            print(f"❌ API Error: {data}")
                            return None
                    except:
                        print(f"⚠️  JSON Parse Error: {text[:200]}")
                        return None
                else:
                    return None
        else:
            async with session.post(url, json=params, headers=headers) as response:
                text = await response.text()
                print(f"📥 Response: {response.status} - {text[:200]}")
                
                if response.status == 200:
                    try:
                        data = json.loads(text)
                        if data.get('code') == 0:
                            return data.get('data')
                        else:
                            print(f"❌ API Error: {data}")
                            return None
                    except:
                        print(f"⚠️  JSON Parse Error: {text[:200]}")
                        return None
                else:
                    return None
                    
    except Exception as e:
        print(f"💥 Request Error: {str(e)}")
        return None

# ========== FUNÇÕES DE TRADING ==========
async def get_current_price():
    """Obtém preço atual"""
    data = await bingx_request("GET", "/openApi/swap/v2/quote/ticker", {"symbol": SYMBOL})
    
    if data:
        # A API retorna lista ou dict
        if isinstance(data, list) and len(data) > 0:
            price = float(data[0].get('lastPrice', 0))
        elif isinstance(data, dict):
            price = float(data.get('lastPrice', 0))
        else:
            price = 0.0
        
        print(f"💰 Preço: ${price}")
        return price
    
    return 0.0

async def get_balance():
    """Obtém saldo da conta"""
    data = await bingx_request("GET", "/openApi/swap/v2/user/balance", signed=True)
    
    if data and 'balance' in data:
        # 'balance' é uma lista de ativos
        if isinstance(data['balance'], list):
            for asset in data['balance']:
                if asset.get('asset') == 'USDT':
                    balance = float(asset.get('balance', 0))
                    print(f"🏦 Saldo: ${balance}")
                    return balance
    
    return 0.0

async def get_position():
    """Obtém posição atual"""
    data = await bingx_request("GET", "/openApi/swap/v2/user/positions", signed=True)
    
    if data:
        if isinstance(data, list):
            for pos in data:
                if pos.get('symbol') == SYMBOL:
                    print(f"📊 Posição: {pos}")
                    return pos
        elif isinstance(data, dict) and data.get('symbol') == SYMBOL:
            print(f"📊 Posição: {data}")
            return data
    
    return None

async def place_market_order(side: str, quantity: float):
    """Executa ordem de mercado"""
    params = {
        "symbol": SYMBOL,
        "side": side.upper(),
        "type": "MARKET",
        "quantity": round(quantity, 4),
        "positionSide": "LONG" if side.upper() == "BUY" else "SHORT"
    }
    
    print(f"🎯 Ordem: {side} {quantity} ETH")
    
    result = await bingx_request("POST", "/openApi/swap/v2/trade/order", params, signed=True)
    
    if result and 'orderId' in result:
        print(f"✅ Ordem executada: {result['orderId']}")
        return True
    else:
        print(f"❌ Falha na ordem")
        return False

async def close_position(side: str):
    """Fecha posição"""
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        print(f"ℹ️  Sem posição para fechar")
        return True
    
    current_side = "LONG" if float(position['positionAmt']) > 0 else "SHORT"
    
    # Verificar se corresponde
    if (side == "LONG" and current_side == "SHORT") or (side == "SHORT" and current_side == "LONG"):
        print(f"ℹ️  Posição não corresponde")
        return True
    
    quantity = abs(float(position['positionAmt']))
    close_side = "SELL" if current_side == "LONG" else "BUY"
    
    return await place_market_order(close_side, quantity)

async def close_all_positions():
    """Fecha todas as posições"""
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        return True
    
    quantity = abs(float(position['positionAmt']))
    side = "SELL" if float(position['positionAmt']) > 0 else "BUY"
    
    return await place_market_order(side, quantity)

# ========== WEBHOOK HANDLER ==========
router = APIRouter()

@router.post("/webhook")
async def webhook_handler(request: Request):
    """Processa sinais do TradingView"""
    print("\n" + "=" * 50)
    print("📨 WEBHOOK RECEBIDO")
    
    try:
        # Ler body
        body = await request.body()
        message = body.decode('utf-8').strip()
        
        print(f"📝 Mensagem: {message}")
        
        # Verificar formato básico
        if not message.startswith(("ENTER-", "EXIT-")):
            return Response(
                content=json.dumps({"error": "Formato inválido"}),
                media_type="application/json",
                status_code=400
            )
        
        # Extrair ação
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
        else:
            return Response(
                content=json.dumps({"error": "Ação desconhecida"}),
                media_type="application/json",
                status_code=400
            )
        
        print(f"🎯 Ação: {action}")
        
        # Executar ação
        success = False
        
        if action == "ENTER-LONG":
            # Obter saldo e preço
            balance = await get_balance()
            price = await get_current_price()
            
            if balance > 0 and price > 0:
                usd_amount = balance * 0.4  # 40%
                quantity = round(usd_amount / price, 4)
                success = await place_market_order("BUY", quantity)
        
        elif action == "ENTER-SHORT":
            balance = await get_balance()
            price = await get_current_price()
            
            if balance > 0 and price > 0:
                usd_amount = balance * 0.4  # 40%
                quantity = round(usd_amount / price, 4)
                success = await place_market_order("SELL", quantity)
        
        elif action == "EXIT-LONG":
            success = await close_position("LONG")
        
        elif action == "EXIT-SHORT":
            success = await close_position("SHORT")
        
        elif action == "EXIT-ALL":
            success = await close_all_positions()
        
        if success:
            print(f"✅ Ação executada com sucesso")
            return Response(
                content=json.dumps({"status": "success", "action": action}),
                media_type="application/json"
            )
        else:
            print(f"❌ Falha na execução")
            return Response(
                content=json.dumps({"status": "error", "action": action}),
                media_type="application/json",
                status_code=500
            )
            
    except Exception as e:
        print(f"💥 Erro: {str(e)}")
        return Response(
            content=json.dumps({"error": str(e)}),
            media_type="application/json",
            status_code=500
        )

@router.get("/status")
async def status():
    """Health check"""
    try:
        price = await get_current_price()
        return {
            "status": "online",
            "price": price,
            "timestamp": time.time()
        }
    except:
        return {"status": "error"}

@router.get("/test")
async def test():
    """Endpoint de teste"""
    return {
        "service": "BingX Trading Bot",
        "api_key": bool(API_KEY),
        "secret_key": bool(SECRET_KEY),
        "symbol": SYMBOL,
        "timestamp": time.time()
    }

# ========== APP ==========
app = FastAPI()

@app.on_event("startup")
async def startup():
    print("\n✅ Servidor iniciado!")
    print(f"🌐 URL: https://bingx-ultra-fast-trading-bot.onrender.com")
    print(f"📡 Webhook: POST /webhook")
    print(f"🏥 Health: GET /status")
    print("=" * 60)

@app.on_event("shutdown")
async def shutdown():
    print("\n👋 Servidor desligando...")
    global _session
    if _session:
        await _session.close()

app.include_router(router)

@app.get("/")
async def root():
    return {
        "service": "BingX Trading Bot",
        "endpoints": {
            "webhook": "POST /webhook",
            "status": "GET /status",
            "test": "GET /test"
        },
        "instructions": {
            "tradingview": "POST /webhook com {{strategy.order.comment}}",
            "format": "ACTION_BingX_ETH-USDT_BOTNAME_TIMEFRAME_SIGNALID"
        }
    }
