"""
Servidor HTTP com logs detalhados para debug
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
from datetime import datetime

# ========== CONFIGURAÇÃO ==========
API_KEY = os.getenv("BINGX_API_KEY")
SECRET_KEY = os.getenv("BINGX_SECRET_KEY")
SYMBOL = "ETH-USDT"

# ========== SISTEMA DE LOGS ==========
class TradingLogger:
    def __init__(self):
        self.logs = []
        self.max_logs = 100
        
    def log(self, level: str, message: str, data: dict = None):
        """Registra log com timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
            "data": data
        }
        
        print(f"[{timestamp}] [{level}] {message}")
        if data:
            print(f"    Dados: {data}")
        
        self.logs.append(log_entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
    
    def get_recent_logs(self, limit: int = 20):
        """Retorna logs recentes"""
        return self.logs[-limit:] if self.logs else []

logger = TradingLogger()

# ========== CACHE E ESTATÍSTICAS ==========
_cache = {
    "price": {"value": 0.0, "timestamp": 0},
    "balance": {"value": 0.0, "timestamp": 0},
    "position": {"value": None, "timestamp": 0},
}

_metrics = {
    "webhooks_received": 0,
    "trades_executed": 0,
    "errors": 0,
    "start_time": time.time(),
    "last_webhook_time": 0,
    "last_trade_time": 0
}

_processed_signals = set()

# ========== REGEX ==========
SIGNAL_PATTERN = re.compile(
    r'^(ENTER-LONG|EXIT-LONG|ENTER-SHORT|EXIT-SHORT|EXIT-ALL)_'
    r'BingX_ETH-USDT_([^_]+)_(\d+M)_([a-f0-9]+)$'
)

router = APIRouter()

# ========== CLIENTE HTTP ==========
_session = None

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        )
    return _session

def generate_signature(params: Dict) -> str:
    query = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(
        SECRET_KEY.encode(),
        query.encode(),
        hashlib.sha256
    ).hexdigest()

async def bingx_request(method: str, endpoint: str, params=None, signed=False) -> Any:
    """Faz requisição à API BingX com logs detalhados"""
    try:
        session = await get_session()
        url = f"https://open-api.bingx.com{endpoint}"
        
        if params is None:
            params = {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = generate_signature(params)
        
        headers = {"X-BX-APIKEY": API_KEY} if signed else {}
        
        logger.log("DEBUG", f"Enviando requisição para {url}", {
            "method": method,
            "params": params,
            "signed": signed
        })
        
        start_time = time.perf_counter()
        
        async with session.request(
            method=method,
            url=url,
            params=params if method == "GET" else None,
            json=params if method == "POST" else None,
            headers=headers
        ) as response:
            response_time = (time.perf_counter() - start_time) * 1000
            
            if response.status == 200:
                data = await response.json()
                logger.log("DEBUG", f"Resposta recebida em {response_time:.2f}ms", {
                    "endpoint": endpoint,
                    "code": data.get('code'),
                    "has_data": 'data' in data
                })
                
                if data.get('code') == 0:
                    return data.get('data', {})
                else:
                    logger.log("ERROR", f"API retornou erro", {
                        "code": data.get('code'),
                        "msg": data.get('msg'),
                        "endpoint": endpoint
                    })
                    return None
            else:
                logger.log("ERROR", f"HTTP {response.status}", {
                    "endpoint": endpoint,
                    "text": await response.text()
                })
                return None
                
    except Exception as e:
        logger.log("ERROR", f"Erro na requisição", {
            "endpoint": endpoint,
            "error": str(e)
        })
        return None

# ========== FUNÇÕES DE TRADING ==========
async def get_current_price():
    """Obtém preço atual com cache de 5 segundos"""
    now = time.time()
    
    if now - _cache["price"]["timestamp"] < 5:
        return _cache["price"]["value"]
    
    data = await bingx_request("GET", "/openApi/swap/v2/quote/ticker", {"symbol": SYMBOL})
    
    if data:
        if isinstance(data, list) and len(data) > 0:
            ticker = data[0]
        elif isinstance(data, dict):
            ticker = data
        else:
            return 0.0
        
        if 'lastPrice' in ticker:
            price = float(ticker['lastPrice'])
            _cache["price"] = {"value": price, "timestamp": now}
            logger.log("INFO", f"Preço atualizado", {"price": price})
            return price
    
    return 0.0

async def get_balance():
    """Obtém saldo da conta"""
    data = await bingx_request("GET", "/openApi/swap/v2/user/balance", signed=True)
    
    if data and 'balance' in data:
        for asset in data['balance']:
            if asset.get('asset') == 'USDT':
                balance = float(asset.get('balance', 0))
                _cache["balance"] = {"value": balance, "timestamp": time.time()}
                logger.log("INFO", f"Saldo obtido", {"balance": balance})
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
        logger.log("INFO", "Alavancagem configurada para 1x")
    else:
        logger.log("WARNING", "Falha ao configurar alavancagem")

async def get_position():
    """Obtém posição atual"""
    data = await bingx_request("GET", "/openApi/swap/v2/user/positions", signed=True)
    
    if data:
        if isinstance(data, list):
            for pos in data:
                if pos.get('symbol') == SYMBOL:
                    _cache["position"] = {"value": pos, "timestamp": time.time()}
                    return pos
        elif isinstance(data, dict) and data.get('symbol') == SYMBOL:
            _cache["position"] = {"value": data, "timestamp": time.time()}
            return data
    
    _cache["position"] = {"value": None, "timestamp": time.time()}
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
    
    logger.log("INFO", f"Enviando ordem de mercado", {
        "side": side,
        "quantity": quantity,
        "params": params
    })
    
    return await bingx_request("POST", "/openApi/swap/v2/trade/order", params, signed=True)

# ========== PROCESSAMENTO DE SINAIS ==========
async def execute_action(action: str):
    """Executa ação baseada no sinal"""
    logger.log("INFO", f"Iniciando execução da ação", {"action": action})
    
    # Configurar alavancagem em background
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
    
    return {"success": False, "error": f"Ação desconhecida: {action}"}

async def enter_position(side: str):
    """Abre nova posição"""
    try:
        # Obter saldo e preço em paralelo
        balance_task = asyncio.create_task(get_balance())
        price_task = asyncio.create_task(get_current_price())
        
        balance, price = await asyncio.gather(balance_task, price_task)
        
        logger.log("INFO", f"Dados para ordem", {
            "balance": balance,
            "price": price,
            "side": side
        })
        
        if balance <= 0:
            return {"success": False, "error": "Saldo insuficiente"}
        
        if price <= 0:
            return {"success": False, "error": "Preço inválido"}
        
        # Calcular 40% do saldo
        usd_amount = balance * 0.4
        quantity = round(usd_amount / price, 4)
        
        logger.log("INFO", f"Calculando quantidade", {
            "usd_amount": usd_amount,
            "quantity": quantity
        })
        
        if quantity <= 0:
            return {"success": False, "error": "Quantidade inválida"}
        
        # Executar ordem
        order_result = await place_market_order(side, quantity)
        
        if order_result and 'orderId' in order_result:
            logger.log("SUCCESS", f"Ordem executada com sucesso!", {
                "order_id": order_result['orderId'],
                "side": side,
                "quantity": quantity
            })
            _metrics["trades_executed"] += 1
            _metrics["last_trade_time"] = time.time()
            return {"success": True, "order_id": order_result['orderId']}
        else:
            logger.log("ERROR", f"Falha na execução da ordem", {
                "order_result": order_result
            })
            return {"success": False, "error": "Falha na execução da ordem"}
            
    except Exception as e:
        logger.log("ERROR", f"Erro ao abrir posição", {"error": str(e)})
        return {"success": False, "error": str(e)}

async def close_position(side: str):
    """Fecha posição existente"""
    try:
        position = await get_position()
        
        if not position or float(position.get('positionAmt', 0)) == 0:
            return {"success": True, "message": "Nenhuma posição para fechar"}
        
        current_side = "LONG" if float(position['positionAmt']) > 0 else "SHORT"
        
        # Verificar se a posição corresponde ao side
        if (side == "LONG" and current_side == "SHORT") or \
           (side == "SHORT" and current_side == "LONG"):
            return {"success": True, "message": "Posição não corresponde"}
        
        quantity = abs(float(position['positionAmt']))
        close_side = "SELL" if current_side == "LONG" else "BUY"
        
        order_result = await place_market_order(close_side, quantity)
        
        if order_result and 'orderId' in order_result:
            logger.log("SUCCESS", f"Posição fechada com sucesso!", {
                "order_id": order_result['orderId'],
                "side": close_side,
                "quantity": quantity
            })
            _metrics["trades_executed"] += 1
            return {"success": True}
        else:
            return {"success": False, "error": "Falha ao fechar posição"}
            
    except Exception as e:
        logger.log("ERROR", f"Erro ao fechar posição", {"error": str(e)})
        return {"success": False, "error": str(e)}

async def close_all_positions():
    """Fecha todas as posições"""
    position = await get_position()
    
    if not position or float(position.get('positionAmt', 0)) == 0:
        return {"success": True, "message": "Nenhuma posição aberta"}
    
    quantity = abs(float(position['positionAmt']))
    side = "SELL" if float(position['positionAmt']) > 0 else "BUY"
    
    order_result = await place_market_order(side, quantity)
    
    if order_result and 'orderId' in order_result:
        logger.log("SUCCESS", "Todas as posições fechadas")
        return {"success": True}
    else:
        return {"success": False, "error": "Falha ao fechar posições"}

# ========== ENDPOINTS ==========
@router.post("/webhook")
async def webhook_handler(request: Request):
    """Endpoint principal para webhooks"""
    _metrics["webhooks_received"] += 1
    _metrics["last_webhook_time"] = time.time()
    
    start_time = time.perf_counter()
    
    try:
        # Ler corpo da requisição
        body_bytes = await request.body()
        
        if not body_bytes:
            logger.log("WARNING", "Webhook com corpo vazio")
            return Response(
                content=json.dumps({"status": "error", "message": "Empty body"}),
                media_type="application/json",
                status_code=400
            )
        
        # Decodificar mensagem
        try:
            message = body_bytes.decode('utf-8').strip()
        except:
            message = str(body_bytes)
        
        logger.log("INFO", f"Webhook recebido", {
            "message": message,
            "length": len(message)
        })
        
        # Validar formato
        match = SIGNAL_PATTERN.match(message)
        if not match:
            logger.log("ERROR", f"Formato de sinal inválido", {"message": message})
            return Response(
                content=json.dumps({"status": "error", "message": "Invalid signal format"}),
                media_type="application/json",
                status_code=400
            )
        
        # Extrair informações
        action = match.group(1)
        bot_name = match.group(2)
        timeframe = match.group(3)
        signal_id = match.group(4)
        
        logger.log("INFO", f"Sinal analisado", {
            "action": action,
            "bot_name": bot_name,
            "timeframe": timeframe,
            "signal_id": signal_id
        })
        
        # Verificar duplicado
        if signal_id in _processed_signals:
            logger.log("INFO", f"Sinal duplicado ignorado", {"signal_id": signal_id})
            return Response(
                content=json.dumps({"status": "duplicate"}),
                media_type="application/json"
            )
        
        _processed_signals.add(signal_id)
        if len(_processed_signals) > 100:
            _processed_signals.clear()
        
        # Executar ação
        result = await execute_action(action)
        
        execution_time = (time.perf_counter() - start_time) * 1000
        
        if result.get("success"):
            logger.log("SUCCESS", f"Ação executada com sucesso", {
                "action": action,
                "execution_time_ms": execution_time
            })
            
            return Response(
                content=json.dumps({
                    "status": "success",
                    "action": action,
                    "execution_ms": round(execution_time, 2),
                    "signal_id": signal_id
                }),
                media_type="application/json",
                headers={"X-Exec-Time": f"{execution_time:.2f}ms"}
            )
        else:
            logger.log("ERROR", f"Falha na execução da ação", {
                "action": action,
                "error": result.get("error"),
                "execution_time_ms": execution_time
            })
            
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
        logger.log("ERROR", f"Erro inesperado no webhook", {"error": str(e)})
        
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
    """Endpoint de status"""
    return {
        "status": "running",
        "service": "BingX Trading Bot",
        "symbol": SYMBOL,
        "metrics": {
            "webhooks_received": _metrics["webhooks_received"],
            "trades_executed": _metrics["trades_executed"],
            "errors": _metrics["errors"],
            "uptime_seconds": time.time() - _metrics["start_time"]
        },
        "cache": {
            "price": _cache["price"]["value"],
            "balance": _cache["balance"]["value"],
            "has_position": _cache["position"]["value"] is not None
        },
        "timestamp": time.time()
    }

@router.get("/debug")
async def debug():
    """Endpoint de debug"""
    return {
        "environment": {
            "api_key_configured": bool(API_KEY),
            "secret_key_configured": bool(SECRET_KEY),
            "symbol": SYMBOL
        },
        "metrics": _metrics,
        "cache_info": {
            "price_age": time.time() - _cache["price"]["timestamp"],
            "balance_age": time.time() - _cache["balance"]["timestamp"],
            "position_age": time.time() - _cache["position"]["timestamp"]
        },
        "recent_signals": list(_processed_signals)[-10:],
        "log_count": len(logger.logs)
    }

@router.get("/webhook/logs")
async def webhook_logs():
    """Retorna logs recentes"""
    return {
        "logs": logger.get_recent_logs(50),
        "total_logs": len(logger.logs)
    }

@router.get("/test/api")
async def test_api():
    """Testa conexão com a API BingX"""
    try:
        # Teste de ticker
        ticker = await bingx_request("GET", "/openApi/swap/v2/quote/ticker", {"symbol": SYMBOL})
        
        # Teste de saldo (se credenciais existirem)
        balance = None
        if API_KEY and SECRET_KEY:
            balance_data = await bingx_request("GET", "/openApi/swap/v2/user/balance", signed=True)
            if balance_data and 'balance' in balance_data:
                for asset in balance_data['balance']:
                    if asset.get('asset') == 'USDT':
                        balance = float(asset.get('balance', 0))
        
        return {
            "success": True,
            "ticker_available": bool(ticker),
            "balance_available": balance is not None,
            "balance": balance,
            "symbol": SYMBOL,
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": time.time()
        }

# ========== CONFIGURAÇÃO DO APP ==========
app = FastAPI(
    title="BingX Trading Bot - Debug",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware para logar todas as requisições"""
    start_time = time.perf_counter()
    
    response = await call_next(request)
    
    process_time = (time.perf_counter() - start_time) * 1000
    
    # Log apenas para endpoints importantes
    if request.url.path == "/webhook":
        logger.log("DEBUG", f"Requisição {request.method} {request.url.path}", {
            "process_time_ms": process_time,
            "status_code": response.status_code
        })
    
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
    return response

@app.on_event("startup")
async def startup_event():
    """Evento de inicialização"""
    logger.log("INFO", "Servidor iniciando...")
    logger.log("INFO", f"Configuração - Símbolo: {SYMBOL}")
    logger.log("INFO", f"API Key configurada: {'Sim' if API_KEY else 'Não'}")
    logger.log("INFO", f"Secret Key configurada: {'Sim' if SECRET_KEY else 'Não'}")

@app.on_event("shutdown")
async def shutdown_event():
    """Evento de desligamento"""
    logger.log("INFO", "Servidor desligando...")
    global _session
    if _session and not _session.closed:
        await _session.close()

# Incluir rotas
app.include_router(router)

# Rota raiz
@app.get("/")
async def root():
    return {
        "service": "BingX Ultra-Fast Trading Bot",
        "status": "🟢 ONLINE",
        "version": "1.0.0",
        "debug_mode": True,
        "endpoints": {
            "status": "GET /status",
            "debug": "GET /debug",
            "webhook": "POST /webhook",
            "webhook_logs": "GET /webhook/logs",
            "test_api": "GET /test/api"
        },
        "instructions": {
            "tradingview": "Configure webhook para POST /webhook",
            "message_format": "ENTER-LONG_BingX_ETH-USDT_BOTNAME_TIMEFRAME_SIGNALID"
        }
    }
