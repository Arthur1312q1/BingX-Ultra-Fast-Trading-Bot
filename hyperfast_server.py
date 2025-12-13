"""
Servidor HTTP com sistema completo de health checks
"""
import asyncio
import time
import json
import hashlib
import hmac
from typing import Dict, Optional, Any
import aiohttp
from fastapi import FastAPI, Request, APIRouter, Response, BackgroundTasks
import os
import re

# Configurações
API_KEY = os.getenv("BINGX_API_KEY")
SECRET_KEY = os.getenv("BINGX_SECRET_KEY")
SYMBOL = "ETH-USDT"

# Cache de performance
_cache = {
    "price": {"value": 0.0, "timestamp": 0, "ttl": 0.05},  # 50ms
    "balance": {"value": 0.0, "timestamp": 0, "ttl": 0.5},  # 500ms
    "position": {"value": None, "timestamp": 0, "ttl": 0.05},  # 50ms
}

# Contadores para monitoramento
_metrics = {
    "webhooks_received": 0,
    "trades_executed": 0,
    "errors": 0,
    "start_time": time.time()
}

# Processamento de sinais
_processed_signals = set()

# Regex
SIGNAL_PATTERN = re.compile(
    r'^(ENTER-LONG|EXIT-LONG|ENTER-SHORT|EXIT-SHORT|EXIT-ALL)_'
    r'BingX_ETH-USDT_[^_]+_\d+M_[\da-f]+$'
)

router = APIRouter()

# ========== SISTEMA DE HEALTH CHECKS INTERNOS ==========
class HealthMonitor:
    def __init__(self):
        self.last_13s_check = 0
        self.last_31s_check = 0
        self.checks_13s = 0
        self.checks_31s = 0
        
    def check_13s(self):
        """Registra check de 13 segundos"""
        self.last_13s_check = time.time()
        self.checks_13s += 1
        return True
        
    def check_31s(self):
        """Registra check de 31 segundos"""
        self.last_31s_check = time.time()
        self.checks_31s += 1
        return True
        
    def get_status(self):
        """Retorna status do monitor"""
        return {
            "13s": {
                "last_check": self.last_13s_check,
                "checks": self.checks_13s,
                "active": (time.time() - self.last_13s_check) < 20  # 20s de tolerância
            },
            "31s": {
                "last_check": self.last_31s_check,
                "checks": self.checks_31s,
                "active": (time.time() - self.last_31s_check) < 40  # 40s de tolerância
            }
        }

health_monitor = HealthMonitor()

# ========== FUNÇÕES DE TRADING ==========
async def get_session():
    """Sessão HTTP otimizada"""
    # Implementação anterior mantida
    pass

async def bingx_request(method: str, endpoint: str, params=None, signed=False):
    """Requisição à API BingX"""
    # Implementação anterior mantida
    pass

async def get_current_price():
    """Obtém preço atual com cache"""
    cache = _cache["price"]
    now = time.time()
    
    if now - cache["timestamp"] < cache["ttl"]:
        return cache["value"]
    
    try:
        data = await bingx_request("GET", "/openApi/swap/v2/quote/ticker", {"symbol": SYMBOL})
        if data:
            price = float(data.get('lastPrice', 0))
            _cache["price"]["value"] = price
            _cache["price"]["timestamp"] = now
            return price
    except:
        pass
    
    return 0.0

# ... (outras funções de trading mantidas)

# ========== ENDPOINTS DE HEALTH CHECK ==========
@router.get("/health/13s")
async def health_check_13s(background_tasks: BackgroundTasks):
    """Health check interno de 13 segundos"""
    background_tasks.add_task(health_monitor.check_13s)
    
    # Teste rápido da API BingX
    try:
        price = await get_current_price()
        return {
            "status": "ok",
            "check": "13s",
            "price": price > 0,
            "timestamp": time.time(),
            "uptime": time.time() - _metrics["start_time"]
        }
    except Exception as e:
        return {
            "status": "degraded",
            "check": "13s",
            "error": str(e),
            "timestamp": time.time()
        }

@router.get("/health/31s")
async def health_check_31s(background_tasks: BackgroundTasks):
    """Health check interno de 31 segundos"""
    background_tasks.add_task(health_monitor.check_31s)
    
    # Teste mais completo
    try:
        # Testa múltiplos endpoints da BingX
        price_task = asyncio.create_task(get_current_price())
        
        # Teste de conexão básica
        test_url = "https://open-api.bingx.com/openApi/swap/v2/quote/ticker?symbol=ETH-USDT"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
            async with session.get(test_url) as resp:
                api_ok = resp.status == 200
        
        price = await price_task
        
        return {
            "status": "ok",
            "check": "31s",
            "api_connected": api_ok,
            "price_available": price > 0,
            "timestamp": time.time(),
            "metrics": {
                "webhooks": _metrics["webhooks_received"],
                "trades": _metrics["trades_executed"],
                "errors": _metrics["errors"]
            }
        }
    except Exception as e:
        _metrics["errors"] += 1
        return {
            "status": "error",
            "check": "31s",
            "error": str(e),
            "timestamp": time.time()
        }

@router.get("/status")
async def status():
    """Endpoint principal para UptimeRobot"""
    try:
        # Testes simultâneos
        price_task = asyncio.create_task(get_current_price())
        health_status = health_monitor.get_status()
        
        price = await price_task
        
        return {
            "status": "operational",
            "service": "BingX Trading Bot",
            "timestamp": time.time(),
            "uptime": time.time() - _metrics["start_time"],
            "performance": {
                "price_cache_ms": int((time.time() - _cache["price"]["timestamp"]) * 1000),
                "webhooks_processed": _metrics["webhooks_received"],
                "trades_executed": _metrics["trades_executed"]
            },
            "health_checks": health_status,
            "exchange": {
                "connected": price > 0,
                "symbol": SYMBOL,
                "last_price": price
            },
            "keep_alive": {
                "13s_active": health_status["13s"]["active"],
                "31s_active": health_status["31s"]["active"],
                "recommendation": "UptimeRobot deve verificar a cada 1-5 minutos"
            }
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": time.time()
        }

@router.get("/keep-alive/test")
async def keep_alive_test():
    """Endpoint específico para testes de keep-alive"""
    now = time.time()
    
    return {
        "message": "✅ Keep-alive system active",
        "server_time": time.ctime(now),
        "unix_timestamp": now,
        "checks": {
            "13s_last": health_monitor.last_13s_check,
            "31s_last": health_monitor.last_31s_check,
            "13s_active": (now - health_monitor.last_13s_check) < 20,
            "31s_active": (now - health_monitor.last_31s_check) < 40
        },
        "instructions": {
            "internal_13s": "GET /health/13s a cada 13 segundos",
            "internal_31s": "GET /health/31s a cada 31 segundos", 
            "external": "UptimeRobot em GET /status a cada 1-5 minutos",
            "webhook": "TradingView POST /webhook com sinais"
        }
    }

@router.get("/")
async def root():
    """Página inicial com informações completas"""
    return {
        "service": "BingX Ultra-Fast Trading Bot",
        "version": "2.0.0",
        "status": "🟢 OPERATIONAL",
        "features": {
            "speed": "<50ms execution",
            "pair": SYMBOL,
            "leverage": "1x",
            "margin": "40% of balance"
        },
        "endpoints": {
            "webhook": "POST /webhook - TradingView signals",
            "status": "GET /status - Health check (UptimeRobot)",
            "health_13s": "GET /health/13s - Internal keep-alive",
            "health_31s": "GET /health/31s - Internal keep-alive",
            "keep_alive_test": "GET /keep-alive/test - System status"
        },
        "anti_shutdown_system": {
            "internal_13s": "Active every 13 seconds",
            "internal_31s": "Active every 31 seconds", 
            "external_monitor": "Required (UptimeRobot)",
            "render_timeout": "15 minutes without traffic",
            "recommendation": "Use all three methods to prevent shutdown"
        },
        "timestamp": time.time()
    }

# ========== WEBHOOK ENDPOINT ==========
@router.post("/webhook")
async def webhook_handler(request: Request, background_tasks: BackgroundTasks):
    """Processa sinais do TradingView"""
    _metrics["webhooks_received"] += 1
    start_time = time.perf_counter()
    
    try:
        # Implementação do webhook mantida
        # ... (código anterior)
        
        execution_time = (time.perf_counter() - start_time) * 1000
        
        return {
            "status": "success",
            "execution_ms": round(execution_time, 2),
            "timestamp": time.time()
        }
        
    except Exception as e:
        _metrics["errors"] += 1
        execution_time = (time.perf_counter() - start_time) * 1000
        
        return {
            "status": "error",
            "error": str(e),
            "execution_ms": round(execution_time, 2),
            "timestamp": time.time()
        }

# ========== INICIALIZAÇÃO ==========
app = FastAPI(
    title="BingX Ultra-Fast Trading Bot",
    description="Sistema com keep-alive interno para evitar desativação no Render",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

# Middleware
@app.middleware("http")
async def add_headers(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.perf_counter() - start_time) * 1000:.2f}ms"
    response.headers["X-Keep-Alive"] = "13s,31s,external"
    return response

@app.on_event("startup")
async def startup_event():
    print("\n" + "=" * 60)
    print("🔥 SISTEMA ANTI-DESATIVAÇÃO ATIVADO")
    print("=" * 60)
    print("✅ Keep-Alive 13s: /health/13s")
    print("✅ Keep-Alive 31s: /health/31s") 
    print("✅ Status UptimeRobot: /status")
    print("✅ Webhook TradingView: /webhook")
    print("=" * 60)
    print("⚠️  Configure UptimeRobot para: GET /status a cada 1-5 minutos")
    print("=" * 60 + "\n")

app.include_router(router)
