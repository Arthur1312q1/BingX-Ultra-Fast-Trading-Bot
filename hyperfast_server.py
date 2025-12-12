"""
Servidor HTTP otimizado para latência mínima
Compatível com Python 3.13+
"""
import asyncio
import time
import json
import hashlib
import hmac
from typing import Dict, Optional, Any
import aiohttp
from fastapi import FastAPI, Request, APIRouter, Response
import os
import re

# Configurações
API_KEY = os.getenv("BINGX_API_KEY")
SECRET_KEY = os.getenv("BINGX_SECRET_KEY")
SYMBOL = "ETH-USDT"

# Variáveis globais otimizadas
_session = None
_price_cache = {"price": 0.0, "timestamp": 0}
_position_cache = {"position": None, "timestamp": 0}
_balance_cache = {"balance": 0.0, "timestamp": 0}
_processed_signals = set()

# Regex pré-compilado para velocidade máxima
SIGNAL_PATTERN = re.compile(
    r'^(ENTER-LONG|EXIT-LONG|ENTER-SHORT|EXIT-SHORT|EXIT-ALL)_'
    r'BingX_ETH-USDT_[^_]+_\d+M_[\da-f]+$'
)

ACTION_PATTERN = re.compile(r'^(ENTER-LONG|EXIT-LONG|ENTER-SHORT|EXIT-SHORT|EXIT-ALL)')

router = APIRouter()

# --- HTTP Client Otimizado com aiohttp ---
async def get_session():
    """Sessão HTTP otimizada com keep-alive"""
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(
            limit=50,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
            force_close=False,
            use_dns_cache=True,
            ttl_dns_cache=300,
            limit_per_host=20
        )
        _session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(
                total=1.5,
                connect=0.3,
                sock_read=1.0,
                sock_connect=0.3
            ),
            json_serialize=json.dumps
        )
    return _session

def generate_signature(params: Dict) -> str:
    """Geração ultra-rápida de assinatura"""
    query = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(
        SECRET_KEY.encode(),
        query.encode(),
        hashlib.sha256
    ).hexdigest()

async def bingx_request(method: str, endpoint: str, params=None, signed=False) -> Any:
    """Requisição ultra-rápida à API BingX"""
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
        
        headers.update({
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        })
        
        async with session.request(
            method=method.upper(),
            url=url,
            params=params if method.upper() == "GET" else None,
            json=params if method.upper() == "POST" else None,
            headers=headers
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                # A API BingX retorna {"code":0, "msg":"", "data":...}
                if data.get('code') == 0:
                    return data.get('data', {})
    except Exception:
        pass
    return None

# --- Funções de Trading Otimizadas ---
async def get_current_price() -> float:
    """Preço com cache de 50ms - CORRIGIDO"""
    global _price_cache
    now = time.time()
    
    if now - _price_cache["timestamp"] < 0.05:  # 50ms cache
        return _price_cache["price"]
    
    data = await bingx_request("GET", "/openApi/swap/v2/quote/ticker", {"symbol": SYMBOL})
    
    # CORREÇÃO: A API pode retornar dict ou list
    if data:
        if isinstance(data, list) and len(data) > 0:
            # Formato de lista
            ticker = data[0]
        elif isinstance(data, dict):
            # Formato de dicionário único
            ticker = data
        else:
            return 0.0
            
        if 'lastPrice' in ticker:
            price = float(ticker['lastPrice'])
            _price_cache = {"price": price, "timestamp": now}
            return price
    
    return 0.0

async def get_balance() -> float:
    """Saldo com cache de 200ms"""
    global _balance_cache
    now = time.time()
    
    if now - _balance_cache["timestamp"] < 0.2:
        return _balance_cache["balance"]
    
    data = await bingx_request("GET", "/openApi/swap/v2/user/balance", signed=True)
    
    if data and isinstance(data, dict) and 'balance' in data:
        for asset in data['balance']:
            if asset.get('asset') == 'USDT':
                balance = float(asset.get('balance', 0))
                _balance_cache = {"balance": balance, "timestamp": now}
                return balance
    return 0.0

async def set_leverage():
    """Configurar alavancagem 1x - fire and forget"""
    asyncio.create_task(bingx_request("POST", "/openApi/swap/v2/trade/leverage", {
        "symbol": SYMBOL,
        "leverage": 1,
        "side": "LONG"
    }, signed=True))

async def get_position():
    """Posição com cache de 50ms - CORRIGIDO"""
    global _position_cache
    now = time.time()
    
    if now - _position_cache["timestamp"] < 0.05:
        return _position_cache["position"]
    
    data = await bingx_request("GET", "/openApi/swap/v2/user/positions", signed=True)
    
    if data:
        # A API retorna lista de posições
        if isinstance(data, list):
            for pos in data:
                if pos.get('symbol') == SYMBOL:
                    _position_cache = {"position": pos, "timestamp": now}
                    return pos
        # Ou um único dicionário
        elif isinstance(data, dict) and data.get('symbol') == SYMBOL:
            _position_cache = {"position": data, "timestamp": now}
            return data
    
    _position_cache = {"position": None, "timestamp": now}
    return None

async def place_market_order(side: str, quantity: float):
    """Ordem de mercado com execução paralela"""
    params = {
        "symbol": SYMBOL,
        "side": side.upper(),
        "type": "MARKET",
        "quantity": round(quantity, 4),
        "positionSide": "LONG" if side.upper() == "BUY" else "SHORT"
    }
    
    return await bingx_request("POST", "/openApi/swap/v2/trade/order", params, signed=True)

# --- Processador de Sinais Ultra-Rápido ---
async def execute_action(action: str):
    """Executa ação com paralelismo máximo"""
    
    # SET LEVERAGE EM PARALELO (não bloqueante)
    asyncio.create_task(set_leverage())
    
    if action == "ENTER-LONG":
        return await enter_position("BUY")
    
    elif action == "ENTER-SHORT":
        return await enter_position("SELL")
    
    elif action == "EXIT-LONG":
        return await close_position("LONG")
    
    elif action == "EXIT-SHORT":
        return await close_position("SHORT")
    
    elif action == "EXIT-ALL":
        return await close_all_positions()
    
    return {"success": False}

async def enter_position(side: str):
    """Abre posição com paralelismo total"""
    # Executar balance e price em paralelo
    balance_task = asyncio.create_task(get_balance())
    price_task = asyncio.create_task(get_current_price())
    
    balance, price = await asyncio.gather(balance_task, price_task)
    
    if balance <= 0 or price <= 0:
        return {"success": False, "error": "Invalid balance or price"}
    
    # Calcular quantidade (40% do saldo)
    usd_amount = balance * 0.4
    quantity = round(usd_amount / price, 4)
    
    if quantity <= 0:
        return {"success": False, "error": "Invalid quantity"}
    
    # Executar ordem com timeout curto
    order_result = await place_market_order(side, quantity)
    
    # Invalidar caches
    global _position_cache, _balance_cache
    _position_cache["timestamp"] = 0
    _balance_cache["timestamp"] = 0
    
    success = bool(order_result and isinstance(order_result, dict) and 'orderId' in order_result)
    
    return {
        "success": success,
        "side": side,
        "quantity": quantity,
        "order_id": order_result.get('orderId') if success else None
    }

async def close_position(side: str):
    """Fecha posição específica"""
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        return {"success": True, "message": "No position to close"}
    
    current_side = "LONG" if float(position.get('positionAmt', 0)) > 0 else "SHORT"
    
    # Verificar se precisa fechar
    if (side == "LONG" and current_side == "SHORT") or \
       (side == "SHORT" and current_side == "LONG"):
        return {"success": True, "message": "Position side mismatch"}
    
    quantity = abs(float(position.get('positionAmt', 0)))
    close_side = "SELL" if current_side == "LONG" else "BUY"
    
    result = await place_market_order(close_side, round(quantity, 4))
    
    # Invalidar cache
    global _position_cache
    _position_cache["timestamp"] = 0
    
    success = bool(result and isinstance(result, dict) and 'orderId' in result)
    
    return {"success": success}

async def close_all_positions():
    """Fecha todas as posições"""
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        return {"success": True, "message": "No positions"}
    
    quantity = abs(float(position.get('positionAmt', 0)))
    side = "SELL" if float(position.get('positionAmt', 0)) > 0 else "BUY"
    
    result = await place_market_order(side, round(quantity, 4))
    
    # Invalidar cache
    global _position_cache
    _position_cache["timestamp"] = 0
    
    success = bool(result and isinstance(result, dict) and 'orderId' in result)
    
    return {"success": success}

# --- Webhook Endpoint Ultra-Rápido ---
@router.post("/webhook")
async def webhook_handler(request: Request):
    """Endpoint principal otimizado para velocidade máxima"""
    start_time = time.perf_counter()
    
    try:
        # Leitura direta do body
        body_bytes = await request.body()
        
        if not body_bytes:
            return Response(
                content=json.dumps({"status": "error", "message": "Empty body"}),
                media_type="application/json",
                status_code=400
            )
        
        # Decodificação rápida
        try:
            message = body_bytes.decode('utf-8').strip()
        except:
            message = str(body_bytes)
        
        # Verificação rápida do formato
        if not SIGNAL_PATTERN.match(message):
            return Response(
                content=json.dumps({"status": "error", "message": "Invalid signal format"}),
                media_type="application/json",
                status_code=400
            )
        
        # Extrair ação com regex otimizado
        match = ACTION_PATTERN.match(message)
        if not match:
            return Response(
                content=json.dumps({"status": "error", "message": "Invalid action"}),
                media_type="application/json",
                status_code=400
            )
        
        action = match.group(1)
        
        # Verificar duplicado (cache em memória)
        signal_hash = hash(message)
        if signal_hash in _processed_signals:
            return Response(
                content=json.dumps({"status": "duplicate"}),
                media_type="application/json"
            )
        
        # Limitar cache a 1000 entradas
        if len(_processed_signals) >= 1000:
            _processed_signals.clear()
        _processed_signals.add(signal_hash)
        
        # Executar ação
        result = await execute_action(action)
        
        execution_time = (time.perf_counter() - start_time) * 1000
        
        if result.get("success"):
            return Response(
                content=json.dumps({
                    "status": "success",
                    "action": action,
                    "execution_ms": round(execution_time, 2)
                }),
                media_type="application/json",
                headers={
                    "X-Exec-Time": f"{execution_time:.2f}ms",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
        else:
            return Response(
                content=json.dumps({
                    "status": "error",
                    "action": action,
                    "error": result.get("error", "Unknown error"),
                    "execution_ms": round(execution_time, 2)
                }),
                media_type="application/json",
                status_code=500
            )
            
    except Exception as e:
        execution_time = (time.perf_counter() - start_time) * 1000
        return Response(
            content=json.dumps({
                "status": "error",
                "message": str(e),
                "execution_ms": round(execution_time, 2)
            }),
            media_type="application/json",
            status_code=500
        )

@router.get("/status")
async def status():
    """Health check minimalista"""
    try:
        # Testar conexão rápida com BingX
        price_task = asyncio.create_task(get_current_price())
        price = await asyncio.wait_for(price_task, timeout=0.5)
        
        return {
            "status": "ultra_fast",
            "exchange": "BingX",
            "pair": SYMBOL,
            "price": price,
            "target_latency": "<50ms",
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "status": "degraded",
            "exchange": "BingX",
            "pair": SYMBOL,
            "error": str(e),
            "timestamp": time.time()
        }

@router.get("/health/13s")
async def health_13s():
    """Health check de 13 segundos"""
    return {"status": "ok", "check": "13s", "timestamp": time.time()}

@router.get("/health/31s")
async def health_31s():
    """Health check de 31 segundos"""
    try:
        # Teste rápido da API BingX
        data = await bingx_request("GET", "/openApi/swap/v2/quote/ticker", {"symbol": SYMBOL})
        return {
            "status": "ok", 
            "check": "31s", 
            "api": "connected" if data else "disconnected",
            "timestamp": time.time()
        }
    except:
        return {"status": "error", "check": "31s", "timestamp": time.time()}

@router.get("/test")
async def test_endpoint():
    """Endpoint de teste para debug"""
    try:
        price = await get_current_price()
        balance = await get_balance()
        position = await get_position()
        
        return {
            "price": price,
            "balance": balance,
            "position": position,
            "timestamp": time.time()
        }
    except Exception as e:
        return {"error": str(e), "timestamp": time.time()}

# --- Startup Tasks ---
async def startup():
    """Tarefas de inicialização"""
    # Aquecer conexões
    await get_session()
    # Aquecer cache de preço (mas não bloquear startup)
    asyncio.create_task(get_current_price())

# Criar app FastAPI
app = FastAPI(
    title="BingX Ultra-Fast Trading Bot",
    description="High-speed trading bot optimized for Python 3.13+",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

# Middleware para logging rápido
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = (time.perf_counter() - start_time) * 1000
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
    return response

# Adicionar middleware de CORS simplificado
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

@app.on_event("startup")
async def on_startup():
    """Evento de startup do FastAPI"""
    print("🚀 BingX Ultra-Fast Trading Bot starting...")
    print(f"✅ API Key configured: {'Yes' if API_KEY else 'No'}")
    print(f"✅ Symbol: {SYMBOL}")
    await startup()

@app.on_event("shutdown")
async def on_shutdown():
    """Evento de shutdown do FastAPI"""
    global _session
    if _session and not _session.closed:
        await _session.close()
    print("👋 Bot shutting down...")

# Incluir rotas
app.include_router(router)

# Rota raiz
@app.get("/")
async def root():
    return {
        "status": "running",
        "service": "BingX Ultra-Fast Trading Bot",
        "target_speed": "<50ms",
        "pair": SYMBOL,
        "endpoints": {
            "webhook": "POST /webhook",
            "status": "GET /status",
            "test": "GET /test",
            "health_13s": "GET /health/13s",
            "health_31s": "GET /health/31s"
        }
    }
