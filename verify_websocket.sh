#!/usr/bin/env bash
# WebSocket 服務驗證腳本
# 用途：快速驗證 Chicken Game WebSocket 服務是否正常運行

# 不使用 set -e，因為我們要手動處理錯誤

# 顏色定義（使用 printf 而不是 echo -e 以確保相容性）
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 輔助函數：彩色輸出
print_success() {
    printf "${GREEN}✅ $1${NC}\n"
}

print_error() {
    printf "${RED}❌ $1${NC}\n"
}

print_warning() {
    printf "${YELLOW}⚠️  $1${NC}\n"
}

print_info() {
    printf "${BLUE}$1${NC}\n"
}

# 配置
API_URL="http://localhost:8000"
WS_URL="ws://localhost:8000"

echo "🔍 驗證 WebSocket 服務..."
echo ""

# ============================================================
# 1. 檢查 HTTP API 是否運行
# ============================================================
echo "【1】檢查 HTTP API..."

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health" 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" = "200" ]; then
    print_success "HTTP API 正常運行 (200)"
else
    print_error "HTTP API 無回應 (HTTP $HTTP_STATUS)"
    echo ""
    echo "請先啟動服務："
    echo "  ./run_dev.sh"
    echo "或："
    echo "  python main.py"
    exit 1
fi

echo ""

# ============================================================
# 2. 建立測試房間
# ============================================================
echo "【2】建立測試房間..."

RESPONSE=$(curl -s -X POST "$API_URL/api/rooms" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "WebSocket Verification Test",
        "num_rounds": 1,
        "allow_communication": false
    }' 2>/dev/null)

# 解析 JSON（不依賴 jq）
ROOM_ID=$(echo "$RESPONSE" | grep -o '"room_id":"[^"]*"' | head -1 | cut -d'"' -f4)
ROOM_CODE=$(echo "$RESPONSE" | grep -o '"code":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$ROOM_ID" ]; then
    print_error "建立房間失敗"
    echo "API 回應："
    echo "$RESPONSE"
    exit 1
fi

print_success "房間已建立"
echo "   Room ID: $ROOM_ID"
echo "   Code: $ROOM_CODE"

echo ""

# ============================================================
# 3. 測試 WebSocket 連線
# ============================================================
echo "【3】測試 WebSocket 連線..."
echo ""

if ! command -v websocat &> /dev/null; then
    print_warning "未安裝 websocat，無法測試 WebSocket 連線"
    echo ""
    echo "安裝 websocat："
    echo "  macOS: brew install websocat"
    echo "  Linux: cargo install websocat"
    echo "  或手動測試：開啟 test_game_v2.html"
    WS_OK=skipped
else
    # 3a. 先測試 Health Check 端點（不需要 room_id）
    echo "   [測試 1/2] Health check 端點 (/ws/health)..."

    # 使用臨時檔案來捕獲 stderr
    TEMP_ERR=$(mktemp)
    HEALTH_RESPONSE=$(echo "ping" | timeout 3 websocat -n1 "$WS_URL/ws/health" 2>"$TEMP_ERR" || true)
    HEALTH_EXIT_CODE=$?
    HEALTH_STDERR=$(cat "$TEMP_ERR")
    rm -f "$TEMP_ERR"

    echo "      發送: ping"
    echo "      收到: ${HEALTH_RESPONSE:-<無回應>}"

    if echo "$HEALTH_RESPONSE" | grep -q "pong"; then
        print_success "   Health check ping/pong 成功"
        HEALTH_OK=true
    else
        print_error "   Health check 失敗"
        echo "      Exit code: $HEALTH_EXIT_CODE"
        if [ -n "$HEALTH_STDERR" ]; then
            echo "      錯誤訊息: $HEALTH_STDERR"
        fi
        if [ $HEALTH_EXIT_CODE -eq 124 ]; then
            echo "      原因：連線 timeout（服務可能沒有啟動或路由錯誤）"
        fi
        HEALTH_OK=false
    fi

    echo ""

    # 3b. 測試實際房間端點
    echo "   [測試 2/2] 房間端點 (/ws/$ROOM_ID)..."

    TEMP_ERR=$(mktemp)
    ROOM_RESPONSE=$(echo "ping" | timeout 3 websocat -n1 "$WS_URL/ws/$ROOM_ID" 2>"$TEMP_ERR" || true)
    ROOM_EXIT_CODE=$?
    ROOM_STDERR=$(cat "$TEMP_ERR")
    rm -f "$TEMP_ERR"

    echo "      發送: ping"
    echo "      收到: ${ROOM_RESPONSE:-<無回應>}"

    if echo "$ROOM_RESPONSE" | grep -q "pong"; then
        print_success "   房間 WebSocket ping/pong 成功"
        ROOM_OK=true
    else
        print_warning "   房間端點無 pong 回應"
        echo "      Exit code: $ROOM_EXIT_CODE"
        if [ -n "$ROOM_STDERR" ]; then
            echo "      錯誤訊息: $ROOM_STDERR"
        fi
        ROOM_OK=false
    fi

    echo ""

    # 綜合判斷
    if [ "$HEALTH_OK" = true ] && [ "$ROOM_OK" = true ]; then
        print_success "WebSocket 所有測試通過"
        WS_OK=true
    elif [ "$HEALTH_OK" = true ]; then
        print_warning "Health check 正常，但房間端點有問題"
        WS_OK=partial
    else
        print_error "WebSocket 測試失敗"
        echo ""
        echo "可能的原因："
        echo "  1. 後端服務未正確啟動（請重啟 ./run_dev.sh）"
        echo "  2. WebSocket 路由未正確註冊"
        echo "  3. 防火牆或代理阻擋 WebSocket 連線"
        echo ""
        WS_OK=false
    fi
fi

echo ""

# ============================================================
# 4. 總結報告
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【總結】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_success "FastAPI 服務正常運行"
print_success "HTTP API 端點可訪問"
print_success "可以建立房間（資料庫正常）"

if [ "$WS_OK" = "true" ]; then
    print_success "WebSocket 端點已驗證（ping/pong 成功）"
elif [ "$WS_OK" = "partial" ]; then
    print_warning "WebSocket 端點部分正常（建議檢查房間端點）"
elif [ "$WS_OK" = "false" ]; then
    print_error "WebSocket 端點測試失敗（請檢查上方錯誤訊息）"
else
    print_warning "WebSocket 端點未測試（需要 websocat）"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【下一步建議】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$WS_OK" = "true" ]; then
    echo "✅ 所有測試通過！可以開始使用："
    echo ""
    echo "1. 開啟測試頁面進行完整功能驗證："
    print_info "   open test_game_v2.html"
    echo ""
    echo "2. 查看 API 文件："
    print_info "   open http://localhost:8000/docs"
elif [ "$WS_OK" = "false" ]; then
    echo "❌ 需要修復 WebSocket 問題："
    echo ""
    echo "1. 重啟後端服務："
    echo "   Ctrl+C 停止當前服務"
    echo "   ./run_dev.sh"
    echo ""
    echo "2. 檢查後端日誌是否有錯誤訊息"
    echo ""
    echo "3. 手動測試 WebSocket："
    print_info "   websocat $WS_URL/ws/health"
    echo "   然後輸入: ping"
    echo "   （應該收到: pong）"
else
    echo "1. 開啟測試頁面進行完整功能驗證："
    print_info "   open test_game_v2.html"
    echo ""
    echo "2. 查看 API 文件："
    print_info "   open http://localhost:8000/docs"
    echo ""
    echo "3. 手動測試 WebSocket（需要 websocat）："
    print_info "   # Health check 端點"
    print_info "   websocat $WS_URL/ws/health"
    print_info "   # 房間端點"
    print_info "   websocat $WS_URL/ws/$ROOM_ID"
    echo "   然後輸入: ping"
fi

echo ""
echo "4. 查看伺服器日誌："
echo "   檢查終端輸出是否有 WebSocket 連線日誌"
echo "   應該看到 'Received ping' 和 'sending pong' 訊息"
echo ""
