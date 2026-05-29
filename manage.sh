#!/bin/bash

# prereview-system 服务管理脚本
# 用法: ./manage.sh [start|stop|restart|status|logs|log-backend|log-frontend]

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

# 加载 .env 配置（如存在）
if [ -f "$BASE_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$BASE_DIR/.env"
    set +a
fi

BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"
LOG_DIR="$BASE_DIR/logs"
BACKEND_PID_FILE="$BASE_DIR/backend.pid"
FRONTEND_PID_FILE="$BASE_DIR/frontend.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

mkdir -p "$LOG_DIR"

# ──────────────────────────────────────────────
_is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

_start_backend() {
    if _is_running "$BACKEND_PID_FILE"; then
        echo "[backend] 已在运行 (PID: $(cat "$BACKEND_PID_FILE"))"
        return
    fi
    echo "[backend] 启动中..."
    cd "$BACKEND_DIR" || exit 1
    nohup python3 app.py >> "$BACKEND_LOG" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"
    echo "[backend] 已启动 (PID: $!, 端口: 5000, 日志: $BACKEND_LOG)"
}

_start_frontend() {
    if _is_running "$FRONTEND_PID_FILE"; then
        echo "[frontend] 已在运行 (PID: $(cat "$FRONTEND_PID_FILE"))"
        return
    fi
    echo "[frontend] 启动中..."
    cd "$FRONTEND_DIR" || exit 1
    nohup npm run dev >> "$FRONTEND_LOG" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"
    echo "[frontend] 已启动 (PID: $!, 端口: 3000, 日志: $FRONTEND_LOG)"
}

_stop_backend() {
    if _is_running "$BACKEND_PID_FILE"; then
        local pid
        pid=$(cat "$BACKEND_PID_FILE")
        # 连同子进程一起杀
        pkill -P "$pid" 2>/dev/null
        kill "$pid" 2>/dev/null
        rm -f "$BACKEND_PID_FILE"
        echo "[backend] 已停止 (PID: $pid)"
    else
        echo "[backend] 未在运行"
        rm -f "$BACKEND_PID_FILE"
    fi
    # 兜底：清理残留的 flask/python 进程（仅限本项目目录）
    pkill -f "python3 app.py" 2>/dev/null || true
}

_stop_frontend() {
    if _is_running "$FRONTEND_PID_FILE"; then
        local pid
        pid=$(cat "$FRONTEND_PID_FILE")
        pkill -P "$pid" 2>/dev/null
        kill "$pid" 2>/dev/null
        rm -f "$FRONTEND_PID_FILE"
        echo "[frontend] 已停止 (PID: $pid)"
    else
        echo "[frontend] 未在运行"
        rm -f "$FRONTEND_PID_FILE"
    fi
    # 兜底：清理 prereview-system vite 进程
    pkill -f "prereview-system/frontend.*vite" 2>/dev/null || true
}

# ──────────────────────────────────────────────
cmd_start() {
    _start_backend
    _start_frontend
    echo ""
    echo "服务已启动:"
    echo "  Backend  → http://localhost:5000"
    echo "  Frontend → http://localhost:3000"
}

cmd_stop() {
    _stop_backend
    _stop_frontend
    echo "所有服务已停止。"
}

cmd_restart() {
    echo "重启服务..."
    cmd_stop
    sleep 1
    cmd_start
}

cmd_status() {
    echo "=== prereview-system 服务状态 ==="
    if _is_running "$BACKEND_PID_FILE"; then
        echo "[backend]  运行中  (PID: $(cat "$BACKEND_PID_FILE"), 端口: 5000)"
    else
        echo "[backend]  已停止"
    fi
    if _is_running "$FRONTEND_PID_FILE"; then
        echo "[frontend] 运行中  (PID: $(cat "$FRONTEND_PID_FILE"), 端口: 3000)"
    else
        echo "[frontend] 已停止"
    fi
}

cmd_logs() {
    echo "====== Backend 日志 (最近 50 行) ======"
    tail -n 50 "$BACKEND_LOG" 2>/dev/null || echo "(暂无日志)"
    echo ""
    echo "====== Frontend 日志 (最近 50 行) ======"
    tail -n 50 "$FRONTEND_LOG" 2>/dev/null || echo "(暂无日志)"
}

cmd_log_backend() {
    echo "====== Backend 日志 (实时追踪, Ctrl+C 退出) ======"
    tail -f "$BACKEND_LOG" 2>/dev/null || echo "(暂无日志)"
}

cmd_log_frontend() {
    echo "====== Frontend 日志 (实时追踪, Ctrl+C 退出) ======"
    tail -f "$FRONTEND_LOG" 2>/dev/null || echo "(暂无日志)"
}

# ──────────────────────────────────────────────
case "${1:-help}" in
    start)        cmd_start ;;
    stop)         cmd_stop ;;
    restart)      cmd_restart ;;
    status)       cmd_status ;;
    logs)         cmd_logs ;;
    log-backend)  cmd_log_backend ;;
    log-frontend) cmd_log_frontend ;;
    *)
        echo "用法: $0 {start|stop|restart|status|logs|log-backend|log-frontend}"
        echo ""
        echo "  start         启动 backend + frontend"
        echo "  stop          停止所有服务"
        echo "  restart       重启所有服务"
        echo "  status        查看运行状态"
        echo "  logs          查看两个服务最近 50 行日志"
        echo "  log-backend   实时追踪 backend 日志"
        echo "  log-frontend  实时追踪 frontend 日志"
        ;;
esac
