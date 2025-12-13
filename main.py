#!/usr/bin/env python3
"""
BingX Ultra-Fast Trading Bot - DEBUG MODE
"""
import os
import sys
import asyncio
import time
import json

print("=" * 70)
print("🛠️  BINGX TRADING BOT - MODO DEBUG")
print("=" * 70)

# Verificar variáveis de ambiente
print("🔍 Verificando variáveis de ambiente...")
print(f"BINGX_API_KEY: {'✅ CONFIGURADO' if os.getenv('BINGX_API_KEY') else '❌ NÃO CONFIGURADO'}")
print(f"BINGX_SECRET_KEY: {'✅ CONFIGURADO' if os.getenv('BINGX_SECRET_KEY') else '❌ NÃO CONFIGURADO'}")
print(f"PORT: {os.getenv('PORT', '8000')}")

if not os.getenv('BINGX_API_KEY') or not os.getenv('BINGX_SECRET_KEY'):
    print("\n❌ ERRO CRÍTICO: Credenciais da API não configuradas!")
    print("Configure no Render Dashboard → Environment:")
    print("1. BINGX_API_KEY")
    print("2. BINGX_SECRET_KEY")
    sys.exit(1)

# Importar app
from hyperfast_server import app
from hyperfast_server import bingx_request, get_current_price, get_balance

async def test_api_connection():
    """Testa conexão com a API BingX"""
    print("\n🔌 Testando conexão com BingX API...")
    try:
        # Teste 1: API pública (ticker)
        print("📡 Testando endpoint público...")
        ticker = await bingx_request("GET", "/openApi/swap/v2/quote/ticker", {"symbol": "ETH-USDT"})
        print(f"✅ Ticker: {ticker}")
        
        # Teste 2: Preço atual
        print("💰 Testando preço atual...")
        price = await get_current_price()
        print(f"✅ Preço ETH-USDT: ${price}")
        
        # Teste 3: Saldo da conta
        print("🏦 Testando saldo da conta...")
        balance = await get_balance()
        print(f"✅ Saldo USDT: ${balance}")
        
        return True
    except Exception as e:
        print(f"❌ Erro na conexão com BingX: {str(e)}")
        return False

async def main():
    """Função principal de debug"""
    print("\n🚀 Iniciando servidor em modo debug...")
    
    # Testar conexão com BingX
    if not await test_api_connection():
        print("\n⚠️  AVISO: Conexão com BingX falhou. Verifique:")
        print("1. Credenciais da API estão corretas?")
        print("2. A conta tem permissões para Futures?")
        print("3. API está ativa na conta BingX?")
    
    # Iniciar servidor
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    print(f"\n🌐 Servidor iniciando em: http://0.0.0.0:{port}")
    print(f"🌐 URL externa: https://bingx-ultra-fast-trading-bot.onrender.com")
    print(f"📊 Endpoints disponíveis:")
    print(f"   • GET  /status       - Status do bot")
    print(f"   • GET  /debug        - Informações detalhadas")
    print(f"   • GET  /test/api     - Teste da API BingX")
    print(f"   • POST /webhook      - Webhook do TradingView")
    print(f"   • GET  /webhook/logs - Logs recentes")
    print("\n📢 AGUARDANDO SINAIS DO TRADINGVIEW...")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        workers=1,
        access_log=True,  # Ativar logs de acesso
        timeout_keep_alive=30,
        log_level="info"
    )

if __name__ == "__main__":
    asyncio.run(main())
