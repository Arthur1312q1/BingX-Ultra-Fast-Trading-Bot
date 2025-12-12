"""
Servidor HTTP otimizado para latência mínima
"""
import asyncio
import time
import ujson as json
import hashlib
import hmac
from typing import Dict, Optional
import aiohttp
from fastapi import FastAPI, Request, APIRouter, HTTPException
from fastapi.responses import Response
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

# --- HTTP Client Otimizado ---
async def get_session():
    """Sessão HTTP otimizada com keep-alive"""
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(
            limit=20,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
            force_close=False,
            use_dns_cache=True
        )
        _session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=1.5, connect=0.5),
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

async def bingx_request(method: str, endpoint: str, params=None, signed=False):
    """Requisição ultra-rápida à API BingX"""
    try:
        session = await get_session()
        url = f"https://open-api.bingx.com{endpoint}"
        
        if params is None:
            params = {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = generate_signature(params)
        
        headers = {"X-BX-APIKEY": API_KEY} if signed else {}
        
        async with session.request(
            method=method.upper(),
            url=url,
            params=params if method.upper() == "GET" else None,
            data=params if method.upper() == "POST" else None,
            headers=headers
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('data', {}) if data.get('code') == 0 else {}
    except:
        pass
    return {}

# --- Funções de Trading Otimizadas ---
async def get_current_price():
    """Preço com cache de 100ms"""
    global _price_cache
    now = time.time()
    
    if now - _price_cache["timestamp"] < 0.1:  # 100ms cache
        return _price_cache["price"]
    
    data = await bingx_request("GET", "/openApi/swap/v2/quote/ticker", {"symbol": SYMBOL})
    if data and data[0].get('lastPrice'):
        price = float(data[0]['lastPrice'])
        _price_cache = {"price": price, "timestamp": now}
        return price
    return 0.0

async def get_balance():
    """Saldo com cache de 500ms"""
    global _balance_cache
    now = time.time()
    
    if now - _balance_cache["timestamp"] < 0.5:
        return _balance_cache["balance"]
    
    data = await bingx_request("GET", "/openApi/swap/v2/user/balance", signed=True)
    if data and 'balance' in data:
        for asset in data['balance']:
            if asset['asset'] == 'USDT':
                balance = float(asset['balance'])
                _balance_cache = {"balance": balance, "timestamp": now}
                return balance
    return 0.0

async def set_leverage():
    """Configurar alavancagem 1x (cache por sessão)"""
    await bingx_request("POST", "/openApi/swap/v2/trade/leverage", {
        "symbol": SYMBOL,
        "leverage": 1,
        "side": "LONG"
    }, signed=True)

async def get_position():
    """Posição com cache de 100ms"""
    global _position_cache
    now = time.time()
    
    if now - _position_cache["timestamp"] < 0.1:
        return _position_cache["position"]
    
    data = await bingx_request("GET", "/openApi/swap/v2/user/positions", signed=True)
    if data:
        for pos in data:
            if pos['symbol'] == SYMBOL:
                _position_cache = {"position": pos, "timestamp": now}
                return pos
    
    _position_cache = {"position": None, "timestamp": now}
    return None

async def place_market_order(side: str, quantity: float):
    """Ordem de mercado com timeout agressivo"""
    params = {
        "symbol": SYMBOL,
        "side": side.upper(),
        "type": "MARKET",
        "quantity": quantity,
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
        return {"success": False}
    
    # Calcular quantidade (40% do saldo)
    usd_amount = balance * 0.4
    quantity = round(usd_amount / price, 4)
    
    if quantity <= 0:
        return {"success": False}
    
    # Executar ordem
    order_result = await place_market_order(side, quantity)
    
    # Invalidar caches
    global _position_cache, _balance_cache
    _position_cache["timestamp"] = 0
    _balance_cache["timestamp"] = 0
    
    return {
        "success": bool(order_result and 'orderId' in order_result),
        "side": side,
        "quantity": quantity
    }

async def close_position(side: str):
    """Fecha posição específica"""
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        return {"success": True}
    
    current_side = "LONG" if float(position['positionAmt']) > 0 else "SHORT"
    
    # Verificar se precisa fechar
    if (side == "LONG" and current_side == "SHORT") or \
       (side == "SHORT" and current_side == "LONG"):
        return {"success": True}
    
    quantity = abs(float(position['positionAmt']))
    close_side = "SELL" if current_side == "LONG" else "BUY"
    
    result = await place_market_order(close_side, quantity)
    
    # Invalidar cache
    global _position_cache
    _position_cache["timestamp"] = 0
    
    return {"success": bool(result and 'orderId' in result)}

async def close_all_positions():
    """Fecha todas as posições"""
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        return {"success": True}
    
    quantity = abs(float(position['positionAmt']))
    side = "SELL" if float(position['positionAmt']) > 0 else "BUY"
    
    result = await place_market_order(side, quantity)
    
    # Invalidar cache
    global _position_cache
    _position_cache["timestamp"] = 0
    
    return {"success": bool(result and 'orderId' in result)}

# --- Webhook Endpoint Ultra-Rápido ---
@router.post("/webhook")
async def webhook_handler(request: Request):
    """Endpoint principal otimizado para velocidade máxima"""
    start_time = time.perf_counter()
    
    try:
        # Leitura direta do body (sem await adicional)
        body = await request.body()
        
        if not body:
            return Response(status_code=400)
        
        # Decodificação rápida
        try:
            message = body.decode('utf-8').strip()
        except:
            message = str(body)
        
        # Verificação rápida do formato
        if not SIGNAL_PATTERN.match(message):
            return Response(status_code=400)
        
        # Extrair ação com regex otimizado
        match = ACTION_PATTERN.match(message)
        if not match:
            return Response(status_code=400)
        
        action = match.group(1)
        
        # Verificar duplicado (cache em memória)
        if message in _processed_signals:
            return Response(
                content=json.dumps({"status": "duplicate"}),
                media_type="application/json"
            )
        
        # Limitar cache a 1000 entradas
        if len(_processed_signals) >= 1000:
            _processed_signals.clear()
        _processed_signals.add(message)
        
        # Executar ação (não esperar por set_leverage)
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
                headers={"X-Exec-Time": f"{execution_time:.2f}ms"}
            )
        else:
            return Response(
                content=json.dumps({
                    "status": "error",
                    "action": action,
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
    return {
        "status": "ultra_fast",
        "exchange": "BingX",
        "pair": SYMBOL,
        "target_latency": "<50ms",
        "uptime": time.time()
    }

# --- Startup Tasks ---
async def startup():
    """Tarefas de inicialização"""
    # Aquecer conexões
    await get_session()
    asyncio.create_task(get_current_price())
    asyncio.create_task(set_leverage())

async def health_check_13s():
    """Health check de 13 segundos"""
    while True:
        await asyncio.sleep(13)
        try:
            await get_session()
        except:
            pass

async def health_check_31s():
    """Health check de 31 segundos"""
    while True:
        await asyncio.sleep(31)
        try:
            await get_current_price()
        except:
            pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan otimizado"""
    # Iniciar tasks em background
    startup_task = asyncio.create_task(startup())
    health_13s = asyncio.create_task(health_check_13s())
    health_31s = asyncio.create_task(health_check_31s())
    
    yield
    
    # Cleanup
    startup_task.cancel()
    health_13s.cancel()
    health_31s.cancel()
    
    if _session and not _session.closed:
        await _session.close()

# Criar app para importação
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.include_router(router)
