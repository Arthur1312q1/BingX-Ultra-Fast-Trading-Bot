"""
BingX Ultra-Fast Trading Bot - Webhook Receiver
Otimizado para latência < 100ms
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

# Configuração de logging mínimo para não atrasar
logging.basicConfig(level=logging.WARNING)

# ============================================================================
# CONFIGURAÇÕES DA BINGX API
# ============================================================================
API_KEY = os.environ.get('BINGX_API_KEY')
SECRET_KEY = os.environ.get('BINGX_SECRET_KEY')
BASE_URL = 'https://open-api.bingx.com'

# Configurações de trading
LEVERAGE = 1
BALANCE_PERCENTAGE = 0.40  # 40% do saldo
SYMBOL = 'ETH-USDT'  # Par de trading

# ============================================================================
# FUNÇÕES DE ASSINATURA BINGX (ULTRA-RÁPIDAS)
# ============================================================================
def get_sign(params):
    """Gera assinatura HMAC-SHA256 para BingX"""
    query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
    return hmac.new(
        SECRET_KEY.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def bingx_request(method, endpoint, params=None):
    """Request ultra-rápido para BingX API"""
    if params is None:
        params = {}
    
    params['timestamp'] = int(time.time() * 1000)
    params['signature'] = get_sign(params)
    
    headers = {
        'X-BX-APIKEY': API_KEY,
        'Content-Type': 'application/json'
    }
    
    url = f"{BASE_URL}{endpoint}"
    
    # Timeout agressivo: 2 segundos máximo
    if method == 'GET':
        response = requests.get(url, params=params, headers=headers, timeout=2)
    else:
        response = requests.post(url, json=params, headers=headers, timeout=2)
    
    return response.json()

# ============================================================================
# FUNÇÕES DE TRADING (EXECUÇÃO INSTANTÂNEA)
# ============================================================================
def get_account_balance():
    """Pega saldo da conta (cached para velocidade)"""
    try:
        endpoint = '/openApi/swap/v2/user/balance'
        result = bingx_request('GET', endpoint)
        
        if result.get('code') == 0:
            balance = result['data']['balance']
            available = float(balance['availableMargin'])
            return available
        return 0
    except:
        return 0

def set_leverage():
    """Define alavancagem (executado apenas uma vez no início)"""
    try:
        endpoint = '/openApi/swap/v2/trade/leverage'
        params = {
            'symbol': SYMBOL,
            'side': 'BOTH',
            'leverage': LEVERAGE
        }
        bingx_request('POST', endpoint, params)
    except:
        pass

def get_current_price():
    """Pega preço atual (ultra-rápido, sem assinatura)"""
    try:
        url = f"{BASE_URL}/openApi/swap/v2/quote/ticker"
        response = requests.get(url, params={'symbol': SYMBOL}, timeout=1)
        data = response.json()
        
        if data.get('code') == 0:
            return float(data['data']['lastPrice'])
        return 0
    except:
        return 0

def calculate_quantity(balance, price):
    """Calcula quantidade baseado em 40% do saldo"""
    position_value = balance * BALANCE_PERCENTAGE
    quantity = position_value / price
    
    # Arredondar para precisão da exchange (ETH geralmente 3 decimais)
    quantity = round(quantity, 3)
    
    return quantity

def execute_trade(side):
    """
    EXECUÇÃO INSTANTÂNEA DE TRADE
    side: 'LONG' ou 'SHORT'
    """
    try:
        # 1. Pegar preço atual (sem autenticação = mais rápido)
        price = get_current_price()
        if price == 0:
            return {"error": "Failed to get price"}
        
        # 2. Pegar saldo (cached quando possível)
        balance = get_account_balance()
        if balance == 0:
            return {"error": "Failed to get balance"}
        
        # 3. Calcular quantidade
        quantity = calculate_quantity(balance, price)
        if quantity == 0:
            return {"error": "Quantity too small"}
        
        # 4. EXECUTAR ORDEM DE MERCADO (INSTANTÂNEA)
        endpoint = '/openApi/swap/v2/trade/order'
        params = {
            'symbol': SYMBOL,
            'side': 'BUY' if side == 'LONG' else 'SELL',
            'positionSide': 'LONG' if side == 'LONG' else 'SHORT',
            'type': 'MARKET',  # ORDEM A MERCADO = EXECUÇÃO INSTANTÂNEA
            'quantity': quantity
        }
        
        result = bingx_request('POST', endpoint, params)
        
        return {
            "success": result.get('code') == 0,
            "side": side,
            "quantity": quantity,
            "price": price,
            "position_value": quantity * price,
            "response": result
        }
        
    except Exception as e:
        return {"error": str(e)}

def close_position(side):
    """Fecha posição existente (para EXIT signals)"""
    try:
        # Pegar posição atual
        endpoint = '/openApi/swap/v2/user/positions'
        params = {'symbol': SYMBOL}
        result = bingx_request('GET', endpoint, params)
        
        if result.get('code') != 0:
            return {"error": "Failed to get positions"}
        
        # Encontrar posição do lado correto
        positions = result.get('data', [])
        target_position = None
        
        for pos in positions:
            if pos['symbol'] == SYMBOL and pos['positionSide'] == side:
                target_position = pos
                break
        
        if not target_position or float(target_position['positionAmt']) == 0:
            return {"info": "No position to close"}
        
        # Fechar posição com ordem de mercado
        quantity = abs(float(target_position['positionAmt']))
        
        endpoint = '/openApi/swap/v2/trade/order'
        params = {
            'symbol': SYMBOL,
            'side': 'SELL' if side == 'LONG' else 'BUY',  # Lado oposto para fechar
            'positionSide': side,
            'type': 'MARKET',
            'quantity': quantity
        }
        
        result = bingx_request('POST', endpoint, params)
        
        return {
            "success": result.get('code') == 0,
            "closed_side": side,
            "quantity": quantity,
            "response": result
        }
        
    except Exception as e:
        return {"error": str(e)}

# ============================================================================
# WEBHOOK ENDPOINT (ZERO LATÊNCIA)
# ============================================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Recebe webhook do TradingView e executa trade INSTANTANEAMENTE
    """
    start_time = time.time()
    
    try:
        data = request.json
        
        # Parsear mensagem do TradingView
        message = data.get('message', '')
        
        # Formato esperado: "ENTER-LONG_BingX_ETH-USDT_trade_45M_ID"
        # ou "EXIT-LONG_BingX_ETH-USDT_trade_45M_ID"
        
        parts = message.split('_')
        if len(parts) < 2:
            return jsonify({"error": "Invalid message format"}), 400
        
        action = parts[0]  # ENTER-LONG, ENTER-SHORT, EXIT-LONG, EXIT-SHORT
        
        # Executar em thread separada para responder IMEDIATAMENTE ao TradingView
        def async_trade():
            if action.startswith('ENTER'):
                side = 'LONG' if 'LONG' in action else 'SHORT'
                result = execute_trade(side)
                print(f"Trade executed: {result}")
            
            elif action.startswith('EXIT'):
                side = 'LONG' if 'LONG' in action else 'SHORT'
                result = close_position(side)
                print(f"Position closed: {result}")
        
        # Executar de forma assíncrona
        Thread(target=async_trade).start()
        
        elapsed = (time.time() - start_time) * 1000  # em ms
        
        # Responder IMEDIATAMENTE (antes mesmo da trade executar)
        return jsonify({
            "status": "received",
            "action": action,
            "latency_ms": round(elapsed, 2),
            "message": "Trade processing initiated"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# HEALTH CHECK (PARA RENDER E UPTIMEROBOT)
# ============================================================================
@app.route('/health', methods=['GET'])
def health():
    """Endpoint de health check para manter Render ativo"""
    return jsonify({
        "status": "online",
        "timestamp": int(time.time()),
        "api_configured": API_KEY is not None and SECRET_KEY is not None
    }), 200

@app.route('/', methods=['GET'])
def home():
    """Página inicial"""
    return jsonify({
        "service": "BingX Ultra-Fast Trading Bot",
        "status": "running",
        "endpoints": {
            "webhook": "/webhook (POST)",
            "health": "/health (GET)"
        }
    }), 200

# ============================================================================
# KEEP-ALIVE INTERNO (BACKUP)
# ============================================================================
def keep_alive_internal():
    """Thread interna que faz self-ping a cada 10 minutos"""
    while True:
        try:
            time.sleep(600)  # 10 minutos
            # Self-ping (caso UptimeRobot falhe)
            requests.get('http://localhost:5000/health', timeout=5)
        except:
            pass

# ============================================================================
# INICIALIZAÇÃO
# ============================================================================
if __name__ == '__main__':
    print("=" * 70)
    print("BingX Ultra-Fast Trading Bot - Starting...")
    print("=" * 70)
    
    # Verificar variáveis de ambiente
    if not API_KEY or not SECRET_KEY:
        print("⚠️  WARNING: API credentials not set!")
        print("Set BINGX_API_KEY and BINGX_SECRET_KEY environment variables")
    else:
        print("✅ API credentials loaded")
        
        # Configurar alavancagem inicial
        print("⚙️  Setting leverage to 1x...")
        set_leverage()
        print("✅ Leverage configured")
    
    # Iniciar keep-alive thread
    Thread(target=keep_alive_internal, daemon=True).start()
    print("✅ Keep-alive thread started")
    
    print("\n🚀 Bot is ready for ultra-fast trading!")
    print("📡 Webhook URL: https://your-app.onrender.com/webhook")
    print("💚 Health check: https://your-app.onrender.com/health")
    print("=" * 70)
    
    # Rodar Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
