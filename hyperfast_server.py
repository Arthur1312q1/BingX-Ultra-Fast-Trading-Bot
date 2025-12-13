"""
Servidor FastAPI para BingX Trading
"""
import asyncio
import time
import json
import hashlib
import hmac
import aiohttp
from fastapi import FastAPI, Request, Response
import os

# Configurações
API_KEY = os.getenv("BINGX_API_KEY")
SECRET_KEY = os.getenv("BINGX_SECRET_KEY")
SYMBOL = "ETH-USDT"

print(f"🔧 Configuração:")
print(f"   Símbolo: {SYMBOL}")
print(f"   API Key: {'✅' if API_KEY else '❌'}")
print(f"   Secret Key: {'✅' if SECRET_KEY else '❌'}")

# Estado global
_session = None
_processed_signals = set()

# ========== FUNÇÕES AUXILIARES ==========
async def get_session():
    """Obtém sessão HTTP"""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session

def generate_signature(params: dict) -> str:
    """Gera assinatura para API BingX"""
    query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
    return hmac.new(
        SECRET_KEY.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

async def bingx_request(method: str, endpoint: str, params=None, signed=False):
    """Faz requisição à API BingX"""
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
        
        print(f"📡 API Request: {method} {endpoint}")
        
        if method.upper() == "GET":
            async with session.get(url, params=params, headers=headers) as response:
                return await handle_response(response, endpoint)
        else:
            async with session.post(url, json=params, headers=headers) as response:
                return await handle_response(response, endpoint)
                
    except Exception as e:
        print(f"❌ Request error: {str(e)}")
        return None

async def handle_response(response, endpoint):
    """Processa resposta da API"""
    text = await response.text()
    print(f"📥 API Response ({endpoint}): {response.status}")
    
    if response.status == 200:
        try:
            data = json.loads(text)
            if data.get('code') == 0:
                return data.get('data')
            else:
                print(f"⚠️ API Error {data.get('code')}: {data.get('msg', 'Unknown error')}")
                return None
        except json.JSONDecodeError:
            print(f"❌ JSON decode error: {text[:100]}")
            return None
    else:
        print(f"❌ HTTP {response.status}: {text[:100]}")
        return None

# ========== FUNÇÕES DE TRADING ==========
async def get_current_price():
    """Obtém preço atual do ETH-USDT"""
    data = await bingx_request("GET", "/openApi/swap/v2/quote/ticker", {"symbol": SYMBOL})
    
    if data:
        # A API retorna lista ou dict
        if isinstance(data, list) and len(data) > 0:
            price = float(data[0].get('lastPrice', 0))
        elif isinstance(data, dict) and 'lastPrice' in data:
            price = float(data.get('lastPrice', 0))
        else:
            return 0.0
        
        print(f"💰 Preço ETH-USDT: ${price}")
        return price
    
    return 0.0

async def get_account_balance():
    """Obtém saldo da conta"""
    data = await bingx_request("GET", "/openApi/swap/v2/user/balance", signed=True)
    
    if data and 'balance' in data:
        for asset in data['balance']:
            if asset.get('asset') == 'USDT':
                balance = float(asset.get('balance', 0))
                print(f"🏦 Saldo USDT: ${balance}")
                return balance
    
    return 0.0

async def set_leverage():
    """Configura alavancagem 1x"""
    result = await bingx_request("POST", "/openApi/swap/v2/trade/leverage", {
        "symbol": SYMBOL,
        "leverage": 1,
        "side": "LONG"
    }, signed=True)
    
    if result:
        print("✅ Alavancagem configurada para 1x")
    else:
        print("⚠️ Não foi possível configurar alavancagem")

async def get_position():
    """Obtém posição atual"""
    data = await bingx_request("GET", "/openApi/swap/v2/user/positions", signed=True)
    
    if data:
        if isinstance(data, list):
            for pos in data:
                if pos.get('symbol') == SYMBOL:
                    return pos
        elif isinstance(data, dict) and data.get('symbol') == SYMBOL:
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
    
    print(f"🎯 Executando ordem: {side.upper()} {quantity} ETH")
    
    result = await bingx_request("POST", "/openApi/swap/v2/trade/order", params, signed=True)
    
    if result and 'orderId' in result:
        print(f"✅ Ordem executada! ID: {result['orderId']}")
        return True
    else:
        print("❌ Falha na execução da ordem")
        return False

# ========== PROCESSAMENTO DE SINAIS ==========
async def process_signal(action: str):
    """Processa sinal recebido"""
    print(f"🎯 Processando ação: {action}")
    
    # Configurar alavancagem em background
    asyncio.create_task(set_leverage())
    
    if action == "ENTER-LONG":
        return await enter_long()
    elif action == "EXIT-LONG":
        return await exit_position("LONG")
    elif action == "ENTER-SHORT":
        return await enter_short()
    elif action == "EXIT-SHORT":
        return await exit_position("SHORT")
    elif action == "EXIT-ALL":
        return await exit_all_positions()
    else:
        return {"success": False, "error": "Ação desconhecida"}

async def enter_long():
    """Abre posição LONG"""
    print("🔓 Abrindo posição LONG...")
    
    # Obter saldo e preço
    balance = await get_account_balance()
    price = await get_current_price()
    
    print(f"📊 Dados: Saldo=${balance}, Preço=${price}")
    
    if balance <= 0 or price <= 0:
        return {"success": False, "error": "Saldo ou preço inválido"}
    
    # Calcular 40% do saldo
    usd_amount = balance * 0.4
    quantity = round(usd_amount / price, 4)
    
    if quantity <= 0:
        return {"success": False, "error": "Quantidade inválida"}
    
    print(f"📈 Quantidade a comprar: {quantity} ETH (${usd_amount})")
    
    # Executar ordem
    success = await place_market_order("BUY", quantity)
    
    return {"success": success}

async def enter_short():
    """Abre posição SHORT"""
    print("🔓 Abrindo posição SHORT...")
    
    balance = await get_account_balance()
    price = await get_current_price()
    
    print(f"📊 Dados: Saldo=${balance}, Preço=${price}")
    
    if balance <= 0 or price <= 0:
        return {"success": False, "error": "Saldo ou preço inválido"}
    
    usd_amount = balance * 0.4
    quantity = round(usd_amount / price, 4)
    
    if quantity <= 0:
        return {"success": False, "error": "Quantidade inválida"}
    
    print(f"📉 Quantidade a vender: {quantity} ETH (${usd_amount})")
    
    success = await place_market_order("SELL", quantity)
    
    return {"success": success}

async def exit_position(side: str):
    """Fecha posição específica"""
    print(f"🔒 Fechando posição {side}...")
    
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        return {"success": True, "message": "Sem posição para fechar"}
    
    current_side = "LONG" if float(position.get('positionAmt', 0)) > 0 else "SHORT"
    
    # Verificar se a posição corresponde
    if (side == "LONG" and current_side == "SHORT") or (side == "SHORT" and current_side == "LONG"):
        return {"success": True, "message": "Posição não corresponde"}
    
    quantity = abs(float(position.get('positionAmt', 0)))
    close_side = "SELL" if current_side == "LONG" else "BUY"
    
    print(f"🔒 Fechando: {quantity} ETH ({current_side} → {close_side})")
    
    success = await place_market_order(close_side, quantity)
    
    return {"success": success}

async def exit_all_positions():
    """Fecha todas as posições"""
    print("🔒 Fechando TODAS as posições...")
    
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        return {"success": True, "message": "Sem posições abertas"}
    
    quantity = abs(float(position.get('positionAmt', 0)))
    side = "SELL" if float(position.get('positionAmt', 0)) > 0 else "BUY"
    
    print(f"🔒 Fechando tudo: {quantity} ETH ({side})")
    
    success = await place_market_order(side, quantity)
    
    return {"success": success}

# ========== APP FASTAPI ==========
app = FastAPI(title="BingX Trading Bot", version="1.0")

@app.on_event("startup")
async def startup():
    """Evento de inicialização"""
    print("\n" + "=" * 60)
    print("✅ SERVIDOR INICIADO COM SUCESSO")
    print("=" * 60)
    print(f"🌐 URL: https://bingx-ultra-fast-trading-bot.onrender.com")
    print(f"📡 Webhook: POST /webhook")
    print(f"🏥 Health: GET /status")
    print("=" * 60 + "\n")

@app.on_event("shutdown")
async def shutdown():
    """Evento de desligamento"""
    print("\n👋 Desligando servidor...")
    global _session
    if _session and not _session.closed:
        await _session.close()

# ========== ROTAS ==========
@app.post("/webhook")
async def webhook(request: Request):
    """Endpoint para webhooks do TradingView"""
    print("\n" + "=" * 50)
    print("📨 WEBHOOK RECEBIDO")
    
    try:
        # Ler mensagem
        body = await request.body()
        message = body.decode('utf-8').strip()
        
        print(f"📝 Mensagem: {message}")
        
        # Verificar formato básico
        if not message or len(message) < 10:
            return Response(
                content=json.dumps({"error": "Mensagem vazia ou muito curta"}),
                media_type="application/json",
                status_code=400
            )
        
        # Extrair ação (simples)
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
                content=json.dumps({"error": "Ação não reconhecida"}),
                media_type="application/json",
                status_code=400
            )
        
        # Verificar duplicado (hash simples)
        msg_hash = hash(message)
        if msg_hash in _processed_signals:
            print("⚠️  Sinal duplicado, ignorando...")
            return Response(
                content=json.dumps({"status": "duplicate"}),
                media_type="application/json"
            )
        
        _processed_signals.add(msg_hash)
        if len(_processed_signals) > 100:
            _processed_signals.clear()
        
        # Processar sinal
        result = await process_signal(action)
        
        if result.get("success"):
            print(f"✅ Ação '{action}' executada com sucesso!")
            return Response(
                content=json.dumps({
                    "status": "success",
                    "action": action,
                    "message": "Trade executado"
                }),
                media_type="application/json"
            )
        else:
            print(f"❌ Falha na ação '{action}': {result.get('error')}")
            return Response(
                content=json.dumps({
                    "status": "error",
                    "action": action,
                    "error": result.get("error", "Erro desconhecido")
                }),
                media_type="application/json",
                status_code=500
            )
            
    except Exception as e:
        print(f"💥 Erro no webhook: {str(e)}")
        return Response(
            content=json.dumps({"error": str(e)}),
            media_type="application/json",
            status_code=500
        )

@app.get("/status")
async def status():
    """Endpoint de health check para Render e UptimeRobot"""
    try:
        price = await get_current_price()
        return {
            "status": "online",
            "service": "BingX Trading Bot",
            "price": price,
            "timestamp": time.time()
        }
    except:
        return {"status": "degraded", "timestamp": time.time()}

@app.get("/")
async def root():
    """Página inicial"""
    return {
        "service": "BingX Ultra-Fast Trading Bot",
        "status": "🟢 ONLINE",
        "endpoints": {
            "webhook": "POST /webhook - Recebe sinais do TradingView",
            "status": "GET /status - Health check",
            "test": "GET /test - Teste de conexão"
        },
        "instructions": {
            "tradingview": "Configure webhook para: https://bingx-ultra-fast-trading-bot.onrender.com/webhook",
            "message": "Use: {{strategy.order.comment}}"
        }
    }

@app.get("/test")
async def test():
    """Endpoint de teste"""
    return {
        "success": True,
        "message": "Bot funcionando!",
        "api_key_configured": bool(API_KEY),
        "secret_key_configured": bool(SECRET_KEY),
        "timestamp": time.time()
    }
