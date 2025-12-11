#!/bin/bash
# 快速測試 WebSocket ping/pong 機制
# 用途：驗證 /ws/health 端點是否正常運作

echo "🧪 快速測試 WebSocket ping/pong..."
echo ""

# 檢查 websocat
if ! command -v websocat &> /dev/null; then
    echo "❌ 未安裝 websocat"
    echo "安裝："
    echo "  macOS: brew install websocat"
    echo "  Linux: cargo install websocat"
    exit 1
fi

# 檢查服務是否運行
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "❌ 服務未運行，請先執行："
    echo "  ./run_dev.sh"
    exit 1
fi

echo "測試 /ws/health 端點..."
echo ""

# 發送 ping，等待 pong
RESPONSE=$(echo "ping" | timeout 2 websocat -n1 ws://localhost:8000/ws/health 2>&1)

echo "發送: ping"
echo "收到: $RESPONSE"
echo ""

if echo "$RESPONSE" | grep -q "pong"; then
    echo "✅ 測試通過！WebSocket ping/pong 正常運作"
    exit 0
else
    echo "❌ 測試失敗！預期收到 'pong'，實際收到 '$RESPONSE'"
    exit 1
fi
