#!/usr/bin/env python3
"""
BingX Ultra-Fast Trading Bot - Sistema Anti-Desativação
Inclui keep-alive interno + externo para evitar shutdown do Render
"""
import os
import sys
import asyncio
import aiohttp
import time
from threading import Thread
import signal

print("=" * 60)
print("🚀 BINGX ULTRA-FAST TRADING BOT - INICIANDO")
print("=" * 60)

# Verificar variáveis de ambiente críticas
required_vars = ['BINGX_API_KEY', 'BINGX_SECRET_KEY']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print(f"❌ ERRO: Variáveis de ambiente ausentes: {', '.join(missing_vars)}")
    print("Configure no Render Dashboard → Environment")
    sys.exit(1)

print(f"✅ Variáveis de ambiente carregadas")
print(f"✅ Python: {sys.version}")
print(f"✅ Porta: {os.getenv('PORT', 8000)}")
print(f"✅ URL Externa: https://bingx-ultra-fast-trading-bot.onrender.com")

# Importar após verificação
from hyperfast_server import app

# --- SISTEMA DE KEEP-ALIVE INTERNO ---
class KeepAliveSystem:
    def __init__(self):
        self.running = True
        self.base_url = f"https://bingx-ultra-fast-trading-bot.onrender.com"
        self.local_url = f"http://localhost:{os.getenv('PORT', 8000)}"
        
        # Contadores para monitoramento
        self.stats = {
            "13s_checks": 0,
            "31s_checks": 0,
            "last_13s": 0,
            "last_31s": 0,
            "errors": 0
        }
    
    async def internal_check_13s(self):
        """Health check interno a cada 13 segundos"""
        while self.running:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                    # Tenta primeiro a URL local
                    try:
                        async with session.get(f"{self.local_url}/health/13s") as resp:
                            if resp.status == 200:
                                self.stats["13s_checks"] += 1
                                self.stats["last_13s"] = time.time()
                                print(f"✅ [13s] Check local OK - Total: {self.stats['13s_checks']}")
                    except:
                        # Se local falhar, tenta externo
                        async with session.get(f"{self.base_url}/health/13s") as resp:
                            if resp.status == 200:
                                self.stats["13s_checks"] += 1
                                self.stats["last_13s"] = time.time()
                                print(f"✅ [13s] Check externo OK - Total: {self.stats['13s_checks']}")
            except Exception as e:
                self.stats["errors"] += 1
                print(f"⚠️ [13s] Erro: {str(e)}")
            
            await asyncio.sleep(13)  # Exato 13 segundos
    
    async def internal_check_31s(self):
        """Health check interno a cada 31 segundos"""
        while self.running:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                    # Alterna entre endpoints
                    endpoints = ["/status", "/health/31s", "/"]
                    endpoint = endpoints[self.stats["31s_checks"] % len(endpoints)]
                    
                    try:
                        async with session.get(f"{self.local_url}{endpoint}") as resp:
                            if resp.status == 200:
                                self.stats["31s_checks"] += 1
                                self.stats["last_31s"] = time.time()
                                print(f"✅ [31s] Check {endpoint} OK - Total: {self.stats['31s_checks']}")
                    except:
                        async with session.get(f"{self.base_url}{endpoint}") as resp:
                            if resp.status == 200:
                                self.stats["31s_checks"] += 1
                                self.stats["last_31s"] = time.time()
                                print(f"✅ [31s] Check {endpoint} OK - Total: {self.stats['31s_checks']}")
            except Exception as e:
                self.stats["errors"] += 1
                print(f"⚠️ [31s] Erro: {str(e)}")
            
            await asyncio.sleep(31)  # Exato 31 segundos
    
    async def external_simulation(self):
        """Simula tráfego externo a cada 5 minutos (300s)"""
        while self.running:
            try:
                # Aguarda 5 minutos
                await asyncio.sleep(300)
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    # Faz uma requisição mais completa para simular usuário real
                    async with session.get(f"{self.base_url}/status") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            print(f"🌐 [EXTERNO] Simulação de tráfego - Status: {data.get('status', 'unknown')}")
            except Exception as e:
                print(f"⚠️ [EXTERNO] Erro na simulação: {str(e)}")
    
    def print_stats(self):
        """Exibe estatísticas periodicamente"""
        while self.running:
            time.sleep(60)  # A cada minuto
            print("\n" + "=" * 50)
            print("📊 ESTATÍSTICAS DO SISTEMA DE KEEP-ALIVE")
            print("=" * 50)
            print(f"✅ Checks 13s: {self.stats['13s_checks']}")
            print(f"✅ Checks 31s: {self.stats['31s_checks']}")
            print(f"⚠️  Erros: {self.stats['errors']}")
            print(f"⏰ Último 13s: {time.ctime(self.stats['last_13s']) if self.stats['last_13s'] else 'Nunca'}")
            print(f"⏰ Último 31s: {time.ctime(self.stats['last_31s']) if self.stats['last_31s'] else 'Nunca'}")
            print(f"🌐 URL Externa: {self.base_url}")
            print("=" * 50 + "\n")
    
    async def start(self):
        """Inicia todos os sistemas de keep-alive"""
        print("\n🔧 INICIANDO SISTEMA ANTI-DESATIVAÇÃO")
        print("----------------------------------------")
        print("✅ Keep-Alive 13s: ATIVADO")
        print("✅ Keep-Alive 31s: ATIVADO") 
        print("✅ Simulação Externa: ATIVADA")
        print("----------------------------------------\n")
        
        # Inicia tarefas em background
        tasks = [
            asyncio.create_task(self.internal_check_13s()),
            asyncio.create_task(self.internal_check_31s()),
            asyncio.create_task(self.external_simulation())
        ]
        
        # Inicia thread para mostrar estatísticas
        stats_thread = Thread(target=self.print_stats, daemon=True)
        stats_thread.start()
        
        # Aguarda todas as tarefas (nunca termina até ser interrompido)
        await asyncio.gather(*tasks)
    
    def stop(self):
        """Para o sistema de keep-alive"""
        self.running = False
        print("\n🛑 Sistema de keep-alive parado")

# --- INICIALIZAÇÃO DO SISTEMA ---
keep_alive = KeepAliveSystem()

# Captura sinais de desligamento
def shutdown_handler(signum, frame):
    print(f"\n⚠️  Recebido sinal {signum}. Desligando graciosamente...")
    keep_alive.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

# Função principal
async def main():
    """Função principal que inicia tudo"""
    # Inicia sistema de keep-alive em background
    keep_alive_task = asyncio.create_task(keep_alive.start())
    
    # Inicia servidor FastAPI
    import uvicorn
    
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        workers=1,
        access_log=False,
        timeout_keep_alive=30,
        log_level="warning",
        loop="asyncio"
    )
    
    server = uvicorn.Server(config)
    
    # Aguarda ambos (servidor + keep-alive)
    await asyncio.gather(server.serve(), keep_alive_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot encerrado pelo usuário")
        keep_alive.stop()
    except Exception as e:
        print(f"\n💥 ERRO CRÍTICO: {str(e)}")
        keep_alive.stop()
        sys.exit(1)
