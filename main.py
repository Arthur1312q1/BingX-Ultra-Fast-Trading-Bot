#!/usr/bin/env python3
"""
BingX Trading Bot - Versão Funcional
"""
import os
import sys

print("=" * 60)
print("🤖 BINGX TRADING BOT - INICIANDO")
print("=" * 60)

# Verificar variáveis
if not os.getenv('BINGX_API_KEY'):
    print("❌ ERRO: BINGX_API_KEY não configurada!")
    print("Configure no Render Dashboard → Environment")
    sys.exit(1)

if not os.getenv('BINGX_SECRET_KEY'):
    print("❌ ERRO: BINGX_SECRET_KEY não configurada!")
    print("Configure no Render Dashboard → Environment")
    sys.exit(1)

print("✅ Credenciais carregadas com sucesso")
print(f"📡 URL: https://bingx-ultra-fast-trading-bot.onrender.com")
print(f"🚪 Porta: {os.getenv('PORT', 8000)}")

# Importar e iniciar servidor
from hyperfast_server import app

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    # Configuração para Render
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        workers=1,
        access_log=True,
        log_level="info"
    )
