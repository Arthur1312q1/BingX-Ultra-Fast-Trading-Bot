#!/usr/bin/env python3
"""
BingX Trading Bot - Docker Version
"""
import os
import sys

print("=" * 60)
print("🐳 BINGX TRADING BOT - DOCKER VERSION")
print("=" * 60)

# Verificar variáveis
if not os.getenv('BINGX_API_KEY'):
    print("❌ ERROR: BINGX_API_KEY not configured!")
    print("Set in Render Dashboard → Environment")
    sys.exit(1)

if not os.getenv('BINGX_SECRET_KEY'):
    print("❌ ERROR: BINGX_SECRET_KEY not configured!")
    print("Set in Render Dashboard → Environment")
    sys.exit(1)

print("✅ API credentials loaded")
print(f"🌐 External URL: https://bingx-ultra-fast-trading-bot.onrender.com")
print(f"🔌 Internal URL: http://0.0.0.0:{os.getenv('PORT', 8000)}")

# Importar app
from hyperfast_server import app

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    # Configuração Docker-friendly
    uvicorn.run(
        app,
        host="0.0.0.0",  # IMPORTANTE: Docker precisa de 0.0.0.0
        port=port,
        workers=1,
        access_log=True,
        log_level="info"
    )
