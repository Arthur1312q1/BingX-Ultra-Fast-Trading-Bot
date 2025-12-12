#!/usr/bin/env python3
"""
BingX Ultra-Fast Trading Bot - Render Optimized
Target: <50ms execution time
Python 3.13+ Compatible
"""
import os
import sys

# Verificar variáveis de ambiente críticas no startup
required_vars = ['BINGX_API_KEY', 'BINGX_SECRET_KEY']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print(f"❌ ERROR: Missing environment variables: {', '.join(missing_vars)}")
    print("Please set these in Render Dashboard → Environment")
    sys.exit(1)

print(f"✅ Environment variables loaded successfully")
print(f"✅ Python version: {sys.version}")
print(f"✅ Bot starting on port: {os.getenv('PORT', 8000)}")

# Agora importar o app
from hyperfast_server import app

# Para execução direta via python main.py
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    # Configurações otimizadas sem uvloop/httptools
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        workers=1,
        access_log=False,
        timeout_keep_alive=5,
        log_level="warning",
        loop="asyncio",
        http="auto"
    )
