#!/bin/bash

# Odoo 服务管理脚本
# 用于多门店管理系统的 Odoo 18.0 服务器管理

ODDO_DIR="/Users/shawnmacmini/code/odoo-18.0"
PORT=8069
DB_NAME="odoo"
DB_USER="odoo"
DB_HOST="localhost"
DB_PORT="5432"

PYTHON_BIN="$ODDO_DIR/.venv/bin/python3"
# 优先使用虚拟环境中的Python以加载项目依赖
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3)"
fi

cd "$ODDO_DIR" || exit 1

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 函数：打印状态信息
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 函数：检查端口是否被占用
check_port() {
    if lsof -i :$PORT &>/dev/null; then
        return 0  # 端口被占用
    else
        return 1  # 端口空闲
    fi
}

# 函数：清理缓存
clean_cache() {
    print_status "正在清理缓存..."

    # 清理 Python 缓存
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    print_status "已清理 Python 缓存"

    # 清理 Odoo 应用缓存
    if [ -d "$HOME/Library/Application Support/Odoo/addons/18.0" ]; then
        rm -rf "$HOME/Library/Application Support/Odoo/addons/18.0/"*
        print_status "已清理 Odoo addons 缓存"
    fi

    # 清理静态文件编译缓存
    if [ -d "$HOME/Library/Application Support/Odoo/filestore" ]; then
        rm -rf "$HOME/Library/Application Support/Odoo/filestore/$DB_NAME"/*
        print_status "已清理 filestore 缓存"
    fi
}

# 函数：启动 Odoo
start_odoo() {
    print_status "启动 Odoo 服务器..."

    # 检查端口是否被占用
    if check_port; then
        print_warning "端口 $PORT 已被占用，正在尝试释放..."
        lsof -i :$PORT | tail -n +2 | awk '{print $2}' | xargs -r kill -9 2>/dev/null || true
        sleep 2
    fi

    # 启动服务器
    nohup "$PYTHON_BIN" odoo-bin \
        --addons-path=addons,$ODDO_DIR/addons,odoo/addons,$ODDO_DIR/addons-custom \
        -d $DB_NAME \
        --db_host=$DB_HOST \
        --db_port=$DB_PORT \
        --db_user=$DB_USER \
        --db_password=$DB_USER \
        --xmlrpc-port=$PORT \
        --log-level=info \
        > odoo.log 2>&1 &

    ODOO_PID=$!
    echo $ODOO_PID > odoo.pid

    print_status "Odoo 已启动，PID: $ODOO_PID"
    print_status "访问地址: http://localhost:$PORT"
    print_status "日志文件: $ODDO_DIR/odoo.log"

    # 等待服务器启动
    sleep 3

    # 检查是否启动成功
    if ps -p $ODOO_PID > /dev/null; then
        print_status "Odoo 启动成功！"
        return 0
    else
        print_error "Odoo 启动失败，请检查日志"
        return 1
    fi
}

# 函数：停止 Odoo
stop_odoo() {
    print_status "停止 Odoo 服务器..."

    if [ -f odoo.pid ]; then
        PID=$(cat odoo.pid)
        if ps -p $PID > /dev/null 2>&1; then
            kill $PID
            sleep 2

            # 如果进程仍然存在，强制杀死
            if ps -p $PID > /dev/null 2>&1; then
                kill -9 $PID
            fi

            print_status "Odoo 已停止"
        else
            print_warning "Odoo 进程不存在"
        fi
        rm -f odoo.pid
    else
        # 尝试通过端口查找并杀死进程
        if check_port; then
            lsof -i :$PORT | tail -n +2 | awk '{print $2}' | xargs -r kill -9
            print_status "Odoo 已停止"
        else
            print_warning "Odoo 未运行"
        fi
    fi
}

# 函数：重启 Odoo
restart_odoo() {
    print_status "重启 Odoo 服务器..."
    stop_odoo
    sleep 2
    clean_cache
    start_odoo
}

# 函数：查看状态
status_odoo() {
    if [ -f odoo.pid ]; then
        PID=$(cat odoo.pid)
        if ps -p $PID > /dev/null 2>&1; then
            print_status "Odoo 正在运行，PID: $PID"
            print_status "访问地址: http://localhost:$PORT"
        else
            print_warning "Odoo 未运行 (PID 文件存在但进程不存在)"
        fi
    elif check_port; then
        print_status "Odoo 正在运行"
        print_status "访问地址: http://localhost:$PORT"
    else
        print_warning "Odoo 未运行"
    fi
}

case "$1" in
    start)
        start_odoo
        ;;
    stop)
        stop_odoo
        ;;
    restart)
        restart_odoo
        ;;
    status)
        status_odoo
        ;;
    clean)
        clean_cache
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|clean}"
        exit 1
        ;;
esac

exit 0
