#!/usr/bin/env python3
"""
Helius ETI监控Webhook接收器
部署到Railway/Heroku等平台即可使用
"""

from flask import Flask, request, jsonify
import requests
import json
import time
from datetime import datetime
import os

app = Flask(__name__)

# 配置 - 从环境变量读取
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '7787266151:AAGzlV_JMek2tcLjN1i0_lve18D54DUaFm8')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID', '-1001817209675')

# DexScreener相关配置
DEXSCREENER_ETI_INDICATORS = {
    # 常见的ETI支付金额（lamports）
    'payment_amounts': [
        2000000000,  # 2 SOL
        5000000000,  # 5 SOL 
        10000000000, # 10 SOL
    ],
    
    # 已知的可能地址（需要研究确定）
    'potential_addresses': [
        # 这些需要通过分析真实ETI支付交易来确定
    ],
    
    # ETI相关的程序
    'programs': [
        'metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s',  # Token Metadata Program
    ]
}

@app.route('/', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "running",
        "service": "ETI Monitor Webhook",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/webhook', methods=['POST'])
def helius_webhook():
    """处理Helius Webhook数据"""
    try:
        data = request.get_json()
        
        # 记录所有接收到的数据（用于调试）
        print(f"\n{'='*50}")
        print(f"收到Webhook数据 - {datetime.now()}")
        print(f"数据: {json.dumps(data, indent=2)}")
        print(f"{'='*50}\n")
        
        # 检测ETI活动
        eti_result = detect_eti_activity(data)
        
        if eti_result['is_eti']:
            print(f"🎯 ETI活动检测到: {eti_result}")
            send_eti_notification(eti_result, data)
        
        return jsonify({"status": "success"}), 200
    
    except Exception as e:
        print(f"❌ Webhook处理错误: {e}")
        return jsonify({"error": str(e)}), 500

def detect_eti_activity(webhook_data):
    """ETI活动检测逻辑"""
    result = {
        'is_eti': False,
        'confidence': 0.0,
        'indicators': [],
        'token_address': None,
        'details': {}
    }
    
    try:
        # 处理Enhanced webhook数据结构
        if isinstance(webhook_data, list):
            transactions = webhook_data
        else:
            transactions = webhook_data.get('data', [webhook_data])
        
        for tx in transactions:
            # 检查交易类型
            tx_type = tx.get('type', '')
            
            # 方法1: 检查TRANSFER类型的交易
            if tx_type == 'TRANSFER':
                transfer_info = tx.get('transfer', {})
                amount = transfer_info.get('amount', 0)
                
                # 检查是否为常见的ETI支付金额
                if amount in DEXSCREENER_ETI_INDICATORS['payment_amounts']:
                    result['indicators'].append('eti_payment_amount')
                    result['confidence'] += 0.4
                    result['details']['payment_amount'] = amount
            
            # 方法2: 检查TOKEN_MINT类型
            elif tx_type == 'TOKEN_MINT':
                result['indicators'].append('token_mint_activity')
                result['confidence'] += 0.2
                
                # 提取token地址
                token_info = tx.get('tokenTransfer', {})
                token_address = token_info.get('mint')
                if token_address:
                    result['token_address'] = token_address
                    
                    # 检查token是否有ETI
                    if check_token_eti_status(token_address):
                        result['indicators'].append('confirmed_eti')
                        result['confidence'] += 0.6
            
            # 方法3: 检查程序调用
            program_info = tx.get('programInfo', {})
            if program_info:
                program_id = program_info.get('programId', '')
                if program_id in DEXSCREENER_ETI_INDICATORS['programs']:
                    result['indicators'].append('metadata_program')
                    result['confidence'] += 0.3
            
            # 方法4: 检查账户地址
            accounts = tx.get('accountData', [])
            for account in accounts:
                account_addr = account.get('account', '')
                if account_addr in DEXSCREENER_ETI_INDICATORS['potential_addresses']:
                    result['indicators'].append('dexscreener_address')
                    result['confidence'] += 0.5
        
        # 判断是否为ETI活动
        result['is_eti'] = result['confidence'] > 0.5
        
        return result
    
    except Exception as e:
        print(f"❌ ETI检测错误: {e}")
        return result

def check_token_eti_status(token_address):
    """检查token的ETI状态"""
    try:
        url = f"https://api.dexscreener.com/orders/v1/solana/{token_address}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            orders = response.json()
            # 如果有订单数据，说明可能有ETI
            return len(orders) > 0
        
        return False
    except:
        return False

def send_eti_notification(eti_result, raw_data):
    """发送ETI通知到Telegram"""
    try:
        # 构建通知消息
        confidence_emoji = "🔥" if eti_result['confidence'] > 0.8 else "⭐"
        
        message = f"{confidence_emoji} <b>ETI活动检测</b>\n\n"
        message += f"🎯 <b>置信度:</b> {eti_result['confidence']*100:.1f}%\n"
        message += f"📊 <b>指标:</b> {', '.join(eti_result['indicators'])}\n"
        
        if eti_result['token_address']:
            message += f"🪙 <b>Token:</b> <code>{eti_result['token_address']}</code>\n"
            message += f"🔗 <b>DexScreener:</b> <a href='https://dexscreener.com/solana/{eti_result['token_address']}'>查看</a>\n"
        
        if eti_result['details'].get('payment_amount'):
            amount_sol = eti_result['details']['payment_amount'] / 1_000_000_000
            message += f"💰 <b>支付金额:</b> {amount_sol} SOL\n"
        
        message += f"\n🕐 <b>时间:</b> {datetime.now().strftime('%H:%M:%S')}"
        message += f"\n⚡ <b>数据源:</b> Helius Webhook"
        
        # 发送到Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            print("✅ Telegram通知发送成功")
        else:
            print(f"❌ Telegram通知发送失败: {response.status_code}")
    
    except Exception as e:
        print(f"❌ 通知发送错误: {e}")

@app.route('/test', methods=['GET'])
def test_notification():
    """测试通知功能"""
    test_result = {
        'is_eti': True,
        'confidence': 0.95,
        'indicators': ['test_mode'],
        'token_address': 'So11111111111111111111111111111111111111112',
        'details': {'payment_amount': 2000000000}
    }
    
    send_eti_notification(test_result, {})
    return jsonify({"message": "测试通知已发送"})

@app.route('/debug', methods=['POST'])
def debug_webhook():
    """调试用的webhook端点"""
    data = request.get_json()
    print("🔍 调试模式 - 收到数据:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    
    return jsonify({
        "received": True,
        "data_type": type(data).__name__,
        "data_size": len(str(data)),
        "timestamp": datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 启动ETI监控Webhook服务器 - 端口: {port}")
    print(f"📱 Telegram通知: {'已配置' if TELEGRAM_BOT_TOKEN else '未配置'}")
    print(f"🔗 Webhook端点: /webhook")
    print(f"🧪 测试端点: /test")
    print(f"🔍 调试端点: /debug")
    
    app.run(host='0.0.0.0', port=port, debug=False)
