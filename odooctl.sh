#!/bin/bash

# Odoo 服务管理脚本（适配 Odoo 16 多门店项目）

set -euo pipefail

ODOO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${CONFIG_FILE:-$ODOO_DIR/odoo.conf}"
PORT="${PORT:-8069}"
DB_NAME="${DB_NAME:-odoo16}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-odoo}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DATA_DIR="${DATA_DIR:-$ODOO_DIR/.odoo-data}"
LOG_FILE="${LOG_FILE:-$ODOO_DIR/odoo.log}"
PID_FILE="${PID_FILE:-$ODOO_DIR/odoo.pid}"

PYTHON_BIN="$ODOO_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="$(command -v python3)"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "[ERROR] 未找到可执行的 Python 解释器，请先创建虚拟环境 .venv"
    exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "[ERROR] 未找到配置文件 $CONFIG_FILE，请先执行数据库初始化任务生成 odoo.conf"
    exit 1
fi

mkdir -p "$DATA_DIR" "$(dirname "$LOG_FILE")"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_port() {
    if lsof -ti :"$PORT" &>/dev/null; then
        return 0
    fi
    return 1
}

clean_cache() {
    local clean_type="${1:-all}"

    print_status "正在清理缓存 (类型: $clean_type)..."

    # 1. 清理 Python 字节码缓存
    if [[ "$clean_type" == "all" || "$clean_type" == "python" ]]; then
        find "$ODOO_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
        find "$ODOO_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        print_status "✓ 已清理 Python 字节码缓存 (.pyc, __pycache__)"
    fi

    # 2. 清理 Session 缓存
    if [[ "$clean_type" == "all" || "$clean_type" == "session" ]]; then
        if [[ -d "$DATA_DIR/sessions" ]]; then
            rm -rf "$DATA_DIR/sessions"/*
            print_status "✓ 已清理 Session 缓存 ($DATA_DIR/sessions)"
        fi
    fi

    # 3. 清理 Assets 缓存（数据库中的编译资源）
    if [[ "$clean_type" == "all" || "$clean_type" == "assets" ]]; then
        print_status "正在清理 Assets 缓存（数据库）..."
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c \
            "DELETE FROM ir_attachment WHERE name LIKE 'web_icon_data%' OR name LIKE '%assets_%' OR url LIKE '/web/content/%';" \
            2>/dev/null && print_status "✓ 已清理 Assets 缓存（数据库 ir_attachment）" || \
            print_warning "⚠ 无法清理 Assets 缓存（可能需要数据库权限）"
    fi

    # 4. 清理 Filestore 缓存（可选，谨慎使用）
    if [[ "$clean_type" == "filestore" ]]; then
        if [[ -d "$DATA_DIR/filestore/$DB_NAME" ]]; then
            print_warning "⚠ 即将删除 filestore，这会删除所有上传的文件！"
            read -p "确认删除？(yes/no): " confirm
            if [[ "$confirm" == "yes" ]]; then
                rm -rf "$DATA_DIR/filestore/$DB_NAME"
                print_status "✓ 已清理 filestore 缓存 ($DATA_DIR/filestore/$DB_NAME)"
            else
                print_status "已取消 filestore 清理"
            fi
        fi
    fi

    print_status "缓存清理完成！"
}

start_odoo() {
    print_status "启动 Odoo 服务器..."

    local pids
    pids=$(lsof -ti :"$PORT" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        print_warning "端口 $PORT 已被占用，尝试杀掉相关进程..."
        for pid in $pids; do
            kill "$pid" 2>/dev/null || true
        done
        sleep 1
    fi

    touch "$LOG_FILE"

    nohup "$PYTHON_BIN" "$ODOO_DIR/odoo-bin" \
        -c "$CONFIG_FILE" \
        -d "$DB_NAME" \
        --db_host="$DB_HOST" \
        --db_port="$DB_PORT" \
        --db_user="$DB_USER" \
        --db_password="$DB_PASSWORD" \
        --xmlrpc-port="$PORT" \
        >>"$LOG_FILE" 2>&1 &

    local odoo_pid=$!
    echo "$odoo_pid" >"$PID_FILE"

    sleep 2

    if ps -p "$odoo_pid" >/dev/null 2>&1; then
        print_status "Odoo 已启动，PID: $odoo_pid"
        print_status "访问地址: http://localhost:$PORT"
        print_status "日志文件: $LOG_FILE"
    else
        print_error "Odoo 启动失败，请查看日志: $LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop_odoo() {
    print_status "停止 Odoo 服务器..."

    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" >/dev/null 2>&1; then
            kill "$pid" 2>/dev/null || true
            sleep 1
            if ps -p "$pid" >/dev/null 2>&1; then
                kill -9 "$pid" 2>/dev/null || true
            fi
            print_status "Odoo 进程已停止 (PID: $pid)"
        else
            print_warning "PID 文件存在但进程已退出"
        fi
        rm -f "$PID_FILE"
    fi

    local pids
    pids=$(lsof -ti :"$PORT" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        for pid in $pids; do
            kill -9 "$pid" 2>/dev/null || true
        done
        print_status "清理占用端口 $PORT 的残留进程"
    fi
}

restart_odoo() {
    local clean_cache_flag="${1:-no}"

    print_status "重启 Odoo 服务器..."
    stop_odoo
    sleep 1

    if [[ "$clean_cache_flag" == "clean" ]]; then
        clean_cache "all"
    fi

    start_odoo
}

dev_restart_odoo() {
    print_status "开发模式重启 Odoo 服务器（清理所有缓存）..."
    stop_odoo
    sleep 1
    clean_cache "all"

    print_status "以开发模式启动 Odoo..."

    local pids
    pids=$(lsof -ti :"$PORT" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        print_warning "端口 $PORT 已被占用，尝试杀掉相关进程..."
        for pid in $pids; do
            kill "$pid" 2>/dev/null || true
        done
        sleep 1
    fi

    touch "$LOG_FILE"

    nohup "$PYTHON_BIN" "$ODOO_DIR/odoo-bin" \
        -c "$CONFIG_FILE" \
        -d "$DB_NAME" \
        --db_host="$DB_HOST" \
        --db_port="$DB_PORT" \
        --db_user="$DB_USER" \
        --db_password="$DB_PASSWORD" \
        --xmlrpc-port="$PORT" \
        --dev=all \
        >>"$LOG_FILE" 2>&1 &

    local odoo_pid=$!
    echo "$odoo_pid" >"$PID_FILE"

    sleep 2

    if ps -p "$odoo_pid" >/dev/null 2>&1; then
        print_status "Odoo 已启动（开发模式），PID: $odoo_pid"
        print_status "访问地址: http://localhost:$PORT"
        print_status "日志文件: $LOG_FILE"
        print_warning "开发模式已启用：自动重载、无缓存、详细日志"
    else
        print_error "Odoo 启动失败，请查看日志: $LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

status_odoo() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" >/dev/null 2>&1; then
            print_status "Odoo 正在运行 (PID: $pid)"
            print_status "访问地址: http://localhost:$PORT"
            return
        else
            print_warning "PID 文件存在但进程已退出"
        fi
    fi

    if check_port; then
        print_status "检测到端口 $PORT 有进程占用，可能为 Odoo"
        lsof -i :"$PORT"
    else
        print_warning "Odoo 未运行"
    fi
}

usage() {
    cat <<EOF
用法: $0 {start|stop|restart|dev-restart|status|clean}

命令说明:
  start           启动 Odoo 服务器
  stop            停止 Odoo 服务器
  restart         重启 Odoo 服务器（不清理缓存）
  restart clean   重启 Odoo 服务器并清理所有缓存
  dev-restart     开发模式重启（清理缓存 + --dev=all）
  status          查看 Odoo 运行状态
  clean [type]    清理缓存
                  - all      清理所有缓存（默认）
                  - python   仅清理 Python 字节码
                  - session  仅清理 Session
                  - assets   仅清理 Assets（数据库）
                  - filestore 清理文件存储（谨慎使用）

开发建议:
  - 开发阶段使用: ./odooctl.sh dev-restart
  - 生产环境使用: ./odooctl.sh restart

示例:
  ./odooctl.sh dev-restart          # 开发模式重启（推荐）
  ./odooctl.sh restart clean        # 普通重启并清理缓存
  ./odooctl.sh clean assets         # 仅清理 Assets 缓存
EOF
    exit 1
}

case "${1:-}" in
    start)
        start_odoo
        ;;
    stop)
        stop_odoo
        ;;
    restart)
        restart_odoo "${2:-no}"
        ;;
    dev-restart)
        dev_restart_odoo
        ;;
    status)
        status_odoo
        ;;
    clean)
        clean_cache "${2:-all}"
        ;;
    *)
        usage
        ;;
esac

exit 0
