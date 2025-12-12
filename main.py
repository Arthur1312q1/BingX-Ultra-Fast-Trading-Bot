#!/usr/bin/env python3
"""
BingX Ultra-Fast Trading Bot
Target: <50ms execution time
"""
import asyncio
import os
import sys
import ujson as json
from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager
import logging

# Otimização máxima - desabilitar logs em produção
logging.getLogger().setLevel(logging.WARNING)

# Importações otimizadas
from hyperfast_server import app, lifespan, startup_tasks

# Configurações de performance
os.environ['PYTHONASYNCIODEBUG'] = '0'
os.environ['UVICORN_ACCESS_LOG'] = '0'

# Criar app com lifespan otimizado
app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

# Incluir rotas do webhook
from hyperfast_server import router
app.include_router(router)

@app.get("/")
async def root():
    return {"status": "ultra-fast", "target": "<50ms"}

if __name__ == "__main__":
    # Configuração ultra-otimizada
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        loop="uvloop",
        http="httptools",
        ws="none",
        lifespan="on",
        access_log=False,
        log_level="warning",
        timeout_keep_alive=5,
        limit_concurrency=1000,
        limit_max_requests=10000,
        reload=False,
        workers=1  # Single worker para evitar race conditions
    )
    
    server = uvicorn.Server(config)
    server.run()
