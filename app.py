"""
BingX Lightning Trade Executor - FINAL OPTIMIZED
Target Latency: < 50ms (ideal: ~10-20ms)

CRITICAL OPTIMIZATIONS:
1. requests.Session() - Persistent TCP connection (saves 10-30ms)
2. Blind Close - No position query for EXIT (saves 100-200ms)
3. Pre-encoded SECRET_KEY - No re-encoding per trade (saves 1-2ms)
4. Global headers in session - No redundant header passing (saves 1-2ms)
5. VPS in Singapore/Hong Kong - RTT 5-20ms to BingX servers

DEPLOYMENT: VPS (Google Cloud/AWS/Oracle) in Singapore or Hong Kong region
"""

from flask import Flask, request, jsonify
import hmac
import hashlib
import time
import requests
import os
from threading import Thread
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.ERROR)

# ============================================================================
# CONFIGURAÇÕES BINGX
# ============================================================================
API_KEY = os.environ.get('BINGX_API_KEY')
SECRET_KEY = os.environ.get('BINGX_SECRET_KEY')
BASE_URL = 'https://open-api.bingx.com'

# PRÉ-CODIFICAÇÃO DA SECRET KEY (Otimização)
SECRET_KEY_ENCODED = SECRET_KEY.encode() if SECRET_KEY else b''

LEVERAGE = 1
SYMBOL = 'ETH-USDT'

# ============================================================================
# SESSÃO PERSISTENTE (OTIMIZAÇÃO CRÍTICA)
# Headers definidos GLOBALMENTE (sem repetição nas chamadas)
# ============================================================================
session = requests.Session()
session.headers.update({
    'X-BX-APIKEY': API_KEY,
    'Content-Type': 'application/json'
})

# ============================================================================
# CACHE GLOBAL
# ============================================================================
price_cache = {'value': 0, 'updated': 0}
balance_cache = {'value': 0, 'updated': 0}

# ============================================================================
# ASSINATURA HMAC (OTIMIZADA)
# ============================================================================
def sign(params):
    """Assinatura HMAC-SHA256 ultra-rápida com SECRET_KEY pré-codificada"""
    query = '&'.join([f"{k}={params[k]}" for k in sorted(params.keys())])
    return hmac.new(SECRET_KEY_ENCODED, query.encode(), hashlib.sha256).hexdigest()

# ============================================================================
# PREÇO (SEM AUTENTICAÇÃO) - USA SESSION
# ============================================================================
def get_price():
    """Pega preço do endpoint público (cache 0.5s) - USA SESSION"""
    now = time.time()
    if now - price_cache['updated'] < 0.5 and price_cache['value'] > 0:
        return price_cache['value']
    
    try:
        # USA SESSION (conexão persistente)
        r = session.get(
            f"{BASE_URL}/openApi/swap/v2/quote/ticker", 
            params={'symbol': SYMBOL}, 
            timeout=1
        )
        data = r.json()
        if data.get('code') == 0:
            price_cache['value'] = float(data['data']['lastPrice'])
            price_cache['updated'] = now
            return price_cache['value']
    except:
        pass
    return price_cache['value'] if price_cache['value'] > 0 else 0

# ============================================================================
# SALDO (CACHE 30s) - USA SESSION
# ============================================================================
def get_balance():
    """Saldo com cache agressivo - USA SESSION"""
    now = time.time()
    if now - balance_cache['updated'] < 30 and balance_cache['value'] > 0:
        return balance_cache['value']
    
    try:
        params = {'timestamp': int(time.time() * 1000)}
        params['signature'] = sign(params)
        
        # USA SESSION (conexão persistente)
        # SEM headers (já definidos globalmente)
        r = session.get(
            f"{BASE_URL}/openApi/swap/v2/user/balance", 
            params=params, 
            timeout=1
        )
        data = r.json()
        if data.get('code') == 0:
            balance_cache['value'] = float(data['data']['balance']['availableMargin'])
            balance_cache['updated'] = now
            return balance_cache['value']
    except:
        pass
    return balance_cache['value'] if balance_cache['value'] > 0 else 0

# ============================================================================
# TRADE INSTANTÂNEO (NÚCLEO ULTRA-OTIMIZADO)
# ============================================================================
def instant_trade(action, quantity):
    """
    EXECUÇÃO INSTANTÂNEA DE TRADE
    action: 'ENTER-LONG', 'ENTER-SHORT', 'EXIT-LONG', 'EXIT-SHORT'
    quantity: float - quantidade ou percentual (depende da ação)
    
    OTIMIZAÇÕES:
    - Blind Close: EXIT não consulta posição (economiza 100-200ms)
    - Session persistente: reutiliza conexão TCP (economiza 10-30ms)
    - Pre-encoded key: não re-codifica a cada trade (economiza 1-2ms)
    - Global headers: sem repetição de headers (economiza 1-2ms)
    """
    start = time.time()
    
    try:
        is_entry = action.startswith('ENTER')
        is_long = 'LONG' in action
        
        print(f"🔄 Starting trade: {action} with quantity {quantity}")
        
        # ====================================================================
        # EXIT: FECHAMENTO CEGO (BLIND CLOSE) - SEM CONSULTA DE POSIÇÃO
        # ====================================================================
        if not is_entry:
            # Quantidade vem direto do TradingView
            qty = quantity
            
            if qty <= 0:
                print(f"❌ Invalid quantity for EXIT: {qty}")
                return False
            
            params = {
                'symbol': SYMBOL,
                'side': 'SELL' if is_long else 'BUY',
                'positionSide': 'LONG' if is_long else 'SHORT',
                'type': 'MARKET',
                'quantity': qty,
                'timestamp': int(time.time() * 1000)
            }
            params['signature'] = sign(params)
            
            print(f"📤 Sending EXIT order to BingX...")
            
            # USA SESSION (conexão persistente)
            # SEM headers (já definidos globalmente)
            r = session.post(
                f"{BASE_URL}/openApi/swap/v2/trade/order",
                json=params,
                timeout=2
            )
            
            elapsed = (time.time() - start) * 1000
            result = r.json()
            
            print(f"📥 BingX response: {result}")
            
            if result.get('code') == 0:
                print(f"⚡ EXIT {'LONG' if is_long else 'SHORT'}: {qty} | {elapsed:.0f}ms")
                return True
            else:
                print(f"❌ EXIT failed: {result}")
                return False
        
        # ====================================================================
        # ENTRY: NOVA POSIÇÃO
        # ====================================================================
        else:
            # Preço (do cache se possível)
            print(f"💰 Getting price...")
            price = get_price()
            if price == 0:
                print("❌ Failed to get price")
                return False
            print(f"✅ Price: ${price}")
            
            # Saldo (do cache se possível)
            print(f"💵 Getting balance...")
            balance = get_balance()
            if balance == 0:
                print("❌ Failed to get balance")
                return False
            print(f"✅ Balance: ${balance}")
            
            # Quantidade: se quantity < 1, é percentual; se >= 1, é quantidade fixa
            if quantity < 1:
                # Percentual do saldo (ex: 0.40 = 40%)
                qty = round((balance * quantity) / price, 3)
            else:
                # Quantidade fixa (ex: 0.156 ETH)
                qty = round(quantity, 3)
            
            if qty <= 0:
                print("❌ Quantity too small")
                return False
            
            print(f"📊 Calculated quantity: {qty} {SYMBOL}")
            
            # ORDEM A MERCADO (INSTANTÂNEA)
            params = {
                'symbol': SYMBOL,
                'side': 'BUY' if is_long else 'SELL',
                'positionSide': 'LONG' if is_long else 'SHORT',
                'type': 'MARKET',
                'quantity': qty,
                'timestamp': int(time.time() * 1000)
            }
            params['signature'] = sign(params)
            
            print(f"📤 Sending ENTRY order to BingX...")
            
            # USA SESSION (conexão persistente)
            # SEM headers (já definidos globalmente)
            r = session.post(
                f"{BASE_URL}/openApi/swap/v2/trade/order",
                json=params,
                timeout=2
            )
            
            elapsed = (time.time() - start) * 1000
            result = r.json()
            
            print(f"📥 BingX response: {result}")
            
            if result.get('code') == 0:
                print(f"⚡ ENTER {'LONG' if is_long else 'SHORT'}: {qty} @ ${price} | {elapsed:.0f}ms")
                return True
            else:
                print(f"❌ Trade failed: {result}")
                return False
                
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"❌ Error after {elapsed:.0f}ms: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# WEBHOOK ENDPOINT (VELOCIDADE MÁXIMA)
# ============================================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    """
    RECEBE MENSAGENS DO TRADINGVIEW
    
    FORMATOS ACEITOS:
    1. {"message": "ENTER-LONG_0.40"}
    2. "ENTER-LONG_0.40"
    3. "ENTER-LONG_BingX_ETH-USDT_trade_45M_ID"
    4. Qualquer string com ENTER-LONG, ENTER-SHORT, EXIT-LONG, EXIT-SHORT
    """
    start = time.time()
    
    try:
        # Tentar pegar dados de múltiplas formas
        message = None
        
        # Tentativa 1: JSON com campo "message"
        try:
            data = request.get_json(force=True)
            if isinstance(data, dict):
                message = data.get('message', '')
            elif isinstance(data, str):
                message = data
        except:
            pass
        
        # Tentativa 2: Texto puro (raw body)
        if not message:
            try:
                message = request.data.decode('utf-8')
            except:
                pass
        
        # Tentativa 3: Form data
        if not message:
            try:
                message = request.form.get('message', '')
            except:
                pass
        
        # Log para debug
        print(f"📨 Received: {message}")
        
        if not message:
            return jsonify({"error": "No message received"}), 400
        
        # Extrair ação (ENTER-LONG, EXIT-SHORT, etc)
        message_upper = message.upper()
        action = None
        
        if 'ENTER-LONG' in message_upper or 'ENTER_LONG' in message_upper:
            action = 'ENTER-LONG'
        elif 'ENTER-SHORT' in message_upper or 'ENTER_SHORT' in message_upper:
            action = 'ENTER-SHORT'
        elif 'EXIT-LONG' in message_upper or 'EXIT_LONG' in message_upper:
            action = 'EXIT-LONG'
        elif 'EXIT-SHORT' in message_upper or 'EXIT_SHORT' in message_upper:
            action = 'EXIT-SHORT'
        
        if not action:
            return jsonify({"error": f"Invalid action in message: {message}"}), 400
        
        # Extrair quantidade (tentar encontrar número após _ ou usar padrão)
        quantity = 0.40  # Padrão: 40% do saldo
        
        if '_' in message:
            parts = message.split('_')
            for part in parts[1:]:  # Ignora primeira parte (ação)
                try:
                    num = float(part)
                    if 0 < num <= 100:  # Número válido encontrado
                        quantity = num if num < 1 else num / 100  # Converte % se necessário
                        break
                except:
                    continue
        
        # Log para debug
        print(f"🎯 Action: {action}, Quantity: {quantity}")
        
        # EXECUTAR EM BACKGROUND
        Thread(target=instant_trade, args=(action, quantity), daemon=True).start()
        
        # RESPONDER INSTANTANEAMENTE
        elapsed = (time.time() - start) * 1000
        return jsonify({
            "status": "executing",
            "action": action,
            "quantity": quantity,
            "latency_ms": round(elapsed, 1)
        }), 200
        
    except Exception as e:
        print(f"❌ Webhook error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# ============================================================================
# HEALTH CHECK
# ============================================================================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "online",
        "timestamp": int(time.time()),
        "cache": {
            "price": price_cache['value'],
            "balance": balance_cache['value']
        },
        "optimization": "Session + Blind Close + Pre-encoded Key + Global Headers"
    }), 200

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "service": "BingX Lightning Executor - FINAL OPTIMIZED",
        "status": "ready",
        "target_latency": "< 50ms (ideal: 10-20ms)",
        "optimizations": [
            "Persistent TCP Session (saves 10-30ms)",
            "Blind Close for EXIT (saves 100-200ms)",
            "Pre-encoded SECRET_KEY (saves 1-2ms)",
            "Global headers in session (saves 1-2ms)",
            "VPS in Singapore/Hong Kong (RTT 5-20ms)"
        ],
        "endpoints": {
            "webhook": "/webhook (POST)",
            "health": "/health (GET)"
        }
    }), 200

# ============================================================================
# KEEP-ALIVE MULTI-THREADED (3 SINAIS DIFERENTES)
# ============================================================================
def keep_alive_primary():
    """Keep-alive primário: a cada 10 minutos"""
    while True:
        try:
            time.sleep(600)  # 10 minutos
            session.get('http://localhost:5000/health', timeout=5)
            print("💚 Keep-alive primary: 10min ping")
        except:
            pass

def keep_alive_secondary():
    """Keep-alive secundário: a cada 13 segundos"""
    while True:
        try:
            time.sleep(13)  # 13 segundos
            session.get('http://localhost:5000/health', timeout=3)
        except:
            pass

def keep_alive_tertiary():
    """Keep-alive terciário: a cada 31 segundos"""
    while True:
        try:
            time.sleep(31)  # 31 segundos
            session.get('http://localhost:5000/health', timeout=3)
        except:
            pass

# ============================================================================
# CONFIGURAÇÃO INICIAL - USA SESSION
# ============================================================================
def setup():
    """Configuração inicial: alavancagem - USA SESSION"""
    try:
        params = {
            'symbol': SYMBOL,
            'side': 'BOTH',
            'leverage': LEVERAGE,
            'timestamp': int(time.time() * 1000)
        }
        params['signature'] = sign(params)
        
        # USA SESSION (conexão persistente)
        # SEM headers (já definidos globalmente)
        session.post(
            f"{BASE_URL}/openApi/swap/v2/trade/leverage",
            json=params,
            timeout=3
        )
        print("✅ Leverage configured")
    except:
        print("⚠️ Leverage setup failed (may already be set)")

# ============================================================================
# INICIALIZAÇÃO
# ============================================================================
if __name__ == '__main__':
    print("=" * 70)
    print("⚡ BingX Lightning Trade Executor - FINAL OPTIMIZED")
    print("=" * 70)
    print(f"📊 Symbol: {SYMBOL}")
    print(f"🎯 Target Latency: < 50ms (ideal: 10-20ms)")
    print("\n🚀 OPTIMIZATIONS ENABLED:")
    print("  ✅ Persistent Session (saves 10-30ms)")
    print("  ✅ Blind Close (saves 100-200ms)")
    print("  ✅ Pre-encoded Key (saves 1-2ms)")
    print("  ✅ Global Headers (saves 1-2ms)")
    print("\n⚠️  DEPLOYMENT REQUIREMENT:")
    print("  📍 Deploy on VPS in Singapore or Hong Kong")
    print("  📍 Google Cloud / AWS / Oracle Cloud Free Tier")
    print("  📍 RTT to BingX: 5-20ms expected")
    print("=" * 70)
    
    if not API_KEY or not SECRET_KEY:
        print("⚠️  API credentials not set!")
    else:
        print("✅ API credentials loaded")
        setup()
    
    # Keep-alive threads (3 sinais diferentes)
    Thread(target=keep_alive_primary, daemon=True).start()
    Thread(target=keep_alive_secondary, daemon=True).start()
    Thread(target=keep_alive_tertiary, daemon=True).start()
    print("✅ Keep-alive active (3 threads: 10min, 13s, 31s)")
    
    # Pre-carregar cache
    print("🔄 Pre-loading cache...")
    get_price()
    get_balance()
    print(f"✅ Price: ${price_cache['value']}")
    print(f"✅ Balance: ${balance_cache['value']}")
    
    print("\n🚀 READY FOR ULTRA-FAST TRADES!")
    print(f"📡 Webhook: http://your-vps-ip:5000/webhook")
    print(f"💚 Health: http://your-vps-ip:5000/health")
    print("\n📝 NEW MESSAGE FORMAT:")
    print('  ENTRY: {"message": "ENTER-LONG_0.40"}   (40% of balance)')
    print('  EXIT:  {"message": "EXIT-LONG_0.156"}   (0.156 ETH)')
    print("=" * 70 + "\n")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
