#!/usr/bin/env python3
"""
BingX Trading Bot - Versão Simplificada
"""
import os
import sys

print("=" * 60)
print("🚀 BINGX TRADING BOT - INICIANDO")
print("=" * 60)

# Verificar variáveis
if not os.getenv('BINGX_API_KEY') or not os.getenv('BINGX_SECRET_KEY'):
    print("❌ ERRO: Configure BINGX_API_KEY e BINGX_SECRET_KEY no Render!")
    sys.exit(1)

print(f"✅ Credenciais configuradas")
print(f"✅ Porta: {os.getenv('PORT', 8000)}")
print(f"✅ URL: https://bingx-ultra-fast-trading-bot.onrender.com")

# Importar app
from hyperfast_server import app

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    # Iniciar servidor simples
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        workers=1,
        access_log=True,
        log_level="info"
    )
