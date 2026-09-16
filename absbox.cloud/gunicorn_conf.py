import multiprocessing
import os
from dotenv import load_dotenv

load_dotenv()
# 监听地址和端口（通常绑定本地，由Nginx转发）
bind = f"0.0.0.0:{os.getenv('PORT', '8001')}"
# 使用Uvicorn的工作进程类
worker_class = "uvicorn.workers.UvicornWorker"
# 工作进程数，推荐为 (CPU核心数 * 2) + 1
workers = multiprocessing.cpu_count() * 1 # + 1
# 每个工作进程的线程数（如果应用支持异步，通常设为1）
threads = 1
# 工作进程的最大同时连接数
worker_connections = 1000
# 超时设置（秒）
timeout = 120
keepalive = 5
# 日志配置
accesslog = "-"  # '-' 表示输出到标准输出
errorlog = "-"
loglevel = "info"
# 进程名
proc_name = "absbox.cloud"
