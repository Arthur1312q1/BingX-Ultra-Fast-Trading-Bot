"""
BingX Lightning Trade Executor
Velocidade EXTREMA: < 0.1s (100ms) total
Otimizado para execução INSTANTÂNEA
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
logging.basicConfig(level=logging.ERROR)  # Apenas erros críticos

# ============================================================================
# CONFIGURAÇÕES BINGX
# ============================================================================
API_KEY = os.environ.get('BINGX_API_KEY')
SECRET_KEY = os.environ.get('BINGX_SECRET_KEY')
BASE_URL = 'https://open-api.bingx.com'

LEVERAGE = 1
BALANCE_PERCENTAGE = 0.40
SYMBOL = 'ETH-USDT'

# ============================================================================
# CACHE GLOBAL (ULTRA-RÁPIDO)
# ============================================================================
price_cache = {'value': 0, 'updated': 0}
balance_cache = {'value': 0, 'updated': 0}

# ============================================================================
# ASSINATURA HMAC (OTIMIZADA)
# ============================================================================
def sign(params):
    """Assinatura HMAC-SHA256 ultra-rápida"""
    query = '&'.join([f"{k}={params[k]}" for k in sorted(params.keys())])
    return hmac.new(SECRET_KEY.encode(), query.encode(), hashlib.sha256).hexdigest()

# ============================================================================
# PREÇO (SEM AUTENTICAÇÃO = INSTANTÂNEO)
# ============================================================================
def get_price():
    """Pega preço do endpoint público (SEM assinatura = +rápido)"""
    now = time.time()
    # Cache de 0.5s (atualiza apenas se muito antigo)
    if now - price_cache['updated'] < 0.5 and price_cache['value'] > 0:
        return price_cache['value']
    
    try:
        r = requests.get(f"{BASE_URL}/openApi/swap/v2/quote/ticker", 
                        params={'symbol': SYMBOL}, timeout=1)
        data = r.json()
        if data.get('code') == 0:
            price_cache['value'] = float(data['data']['lastPrice'])
            price_cache['updated'] = now
            return price_cache['value']
    except:
        pass
    return price_cache['value'] if price_cache['value'] > 0 else 0

# ============================================================================
# SALDO (COM CACHE DE 30s)
# ============================================================================
def get_balance():
    """Saldo com cache agressivo (atualiza apenas a cada 30s)"""
    now = time.time()
    if now - balance_cache['updated'] < 30 and balance_cache['value'] > 0:
        return balance_cache['value']
    
    try:
        params = {'timestamp': int(time.time() * 1000)}
        params['signature'] = sign(params)
        
        r = requests.get(
            f"{BASE_URL}/openApi/swap/v2/user/balance",
            params=params,
            headers={'X-BX-APIKEY': API_KEY},
            timeout=1.5
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
# TRADE INSTANTÂNEO (NÚCLEO DO SISTEMA)
# ============================================================================
def instant_trade(action):
    """
    EXECUÇÃO INSTANTÂNEA DE TRADE
    action: 'ENTER-LONG', 'ENTER-SHORT', 'EXIT-LONG', 'EXIT-SHORT'
    """
    start = time.time()
    
    try:
        # PARSE AÇÃO
        is_entry = action.startswith('ENTER')
        is_long = 'LONG' in action
        
        # EXIT: Fechar posição existente
        if not is_entry:
            params = {
                'symbol': SYMBOL,
                'timestamp': int(time.time() * 1000)
            }
            params['signature'] = sign(params)
            
            # Pega posição atual
            r = requests.get(
                f"{BASE_URL}/openApi/swap/v2/user/positions",
                params=params,
                headers={'X-BX-APIKEY': API_KEY},
                timeout=1.5
            )
            
            positions = r.json().get('data', [])
            target_side = 'LONG' if is_long else 'SHORT'
            position = next((p for p in positions if p['symbol'] == SYMBOL and p['positionSide'] == target_side), None)
            
            if position and float(position['positionAmt']) != 0:
                qty = abs(float(position['positionAmt']))
                
                params = {
                    'symbol': SYMBOL,
                    'side': 'SELL' if is_long else 'BUY',
                    'positionSide': target_side,
                    'type': 'MARKET',
                    'quantity': qty,
                    'timestamp': int(time.time() * 1000)
                }
                params['signature'] = sign(params)
                
                r = requests.post(
                    f"{BASE_URL}/openApi/swap/v2/trade/order",
                    json=params,
                    headers={'X-BX-APIKEY': API_KEY, 'Content-Type': 'application/json'},
                    timeout=1.5
                )
                
                elapsed = (time.time() - start) * 1000
                print(f"⚡ EXIT {target_side}: {qty} @ {elapsed:.0f}ms")
                return True
        
        # ENTRY: Nova posição
        else:
            # 1. Preço (do cache se possível)
            price = get_price()
            if price == 0:
                print("❌ Failed to get price")
                return False
            
            # 2. Saldo (do cache se possível)
            balance = get_balance()
            if balance == 0:
                print("❌ Failed to get balance")
                return False
            
            # 3. Quantidade
            qty = round((balance * BALANCE_PERCENTAGE) / price, 3)
            if qty <= 0:
                print("❌ Quantity too small")
                return False
            
            # 4. ORDEM A MERCADO (INSTANTÂNEA)
            params = {
                'symbol': SYMBOL,
                'side': 'BUY' if is_long else 'SELL',
                'positionSide': 'LONG' if is_long else 'SHORT',
                'type': 'MARKET',
                'quantity': qty,
                'timestamp': int(time.time() * 1000)
            }
            params['signature'] = sign(params)
            
            r = requests.post(
                f"{BASE_URL}/openApi/swap/v2/trade/order",
                json=params,
                headers={'X-BX-APIKEY': API_KEY, 'Content-Type': 'application/json'},
                timeout=1.5
            )
            
            elapsed = (time.time() - start) * 1000
            result = r.json()
            
            if result.get('code') == 0:
                print(f"⚡ ENTER {'LONG' if is_long else 'SHORT'}: {qty} @ ${price} | {elapsed:.0f}ms")
                return True
            else:
                print(f"❌ Trade failed: {result}")
                return False
                
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"❌ Error after {elapsed:.0f}ms: {str(e)}")
        return False

# ============================================================================
# WEBHOOK ENDPOINT (VELOCIDADE MÁXIMA)
# ============================================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    """
    RECEBE {{strategy.order.comment}} DO TRADINGVIEW
    Responde INSTANTANEAMENTE e executa trade em background
    """
    start = time.time()
    
    try:
        data = request.get_json(force=True)
        message = data.get('message', '')
        
        # Parsear mensagem: ENTER-LONG, ENTER-SHORT, EXIT-LONG, EXIT-SHORT
        if not message or '_' not in message:
            return jsonify({"error": "Invalid message"}), 400
        
        action = message.split('_')[0]  # ENTER-LONG, ENTER-SHORT, EXIT-LONG, EXIT-SHORT
        
        # Validar ação
        valid_actions = ['ENTER-LONG', 'ENTER-SHORT', 'EXIT-LONG', 'EXIT-SHORT']
        if action not in valid_actions:
            return jsonify({"error": f"Invalid action: {action}"}), 400
        
        # EXECUTAR EM BACKGROUND (não bloqueia resposta)
        Thread(target=instant_trade, args=(action,), daemon=True).start()
        
        # RESPONDER INSTANTANEAMENTE
        elapsed = (time.time() - start) * 1000
        return jsonify({
            "status": "executing",
            "action": action,
            "latency_ms": round(elapsed, 1)
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# HEALTH CHECK (MANTÉM RENDER ATIVO)
# ============================================================================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "online",
        "timestamp": int(time.time()),
        "cache": {
            "price": price_cache['value'],
            "balance": balance_cache['value']
        }
    }), 200

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "service": "BingX Lightning Executor",
        "status": "ready",
        "target_latency": "< 100ms",
        "endpoints": {
            "webhook": "/webhook (POST)",
            "health": "/health (GET)"
        }
    }), 200

# ============================================================================
# KEEP-ALIVE (EVITA SLEEP DO RENDER)
# ============================================================================
def keep_alive():
    """Self-ping a cada 10 minutos"""
    while True:
        try:
            time.sleep(600)
            requests.get('http://localhost:5000/health', timeout=5)
        except:
            pass

# ============================================================================
# CONFIGURAÇÃO INICIAL
# ============================================================================
def setup():
    """Configuração inicial: alavancagem"""
    try:
        params = {
            'symbol': SYMBOL,
            'side': 'BOTH',
            'leverage': LEVERAGE,
            'timestamp': int(time.time() * 1000)
        }
        params['signature'] = sign(params)
        
        requests.post(
            f"{BASE_URL}/openApi/swap/v2/trade/leverage",
            json=params,
            headers={'X-BX-APIKEY': API_KEY, 'Content-Type': 'application/json'},
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
    print("⚡ BingX Lightning Trade Executor")
    print("=" * 70)
    print(f"📊 Symbol: {SYMBOL}")
    print(f"💰 Position Size: {int(BALANCE_PERCENTAGE*100)}% of balance")
    print(f"🎯 Target Latency: < 100ms")
    print("=" * 70)
    
    if not API_KEY or not SECRET_KEY:
        print("⚠️  API credentials not set!")
    else:
        print("✅ API credentials loaded")
        setup()
    
    # Keep-alive thread
    Thread(target=keep_alive, daemon=True).start()
    print("✅ Keep-alive active")
    
    # Pre-carregar cache
    print("🔄 Pre-loading cache...")
    get_price()
    get_balance()
    print(f"✅ Price: ${price_cache['value']}")
    print(f"✅ Balance: ${balance_cache['value']}")
    
    print("\n🚀 READY FOR LIGHTNING-FAST TRADES!")
    print(f"📡 Webhook: https://your-app.onrender.com/webhook")
    print(f"💚 Health: https://your-app.onrender.com/health")
    print("=" * 70 + "\n")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
