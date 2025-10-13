import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


class LoggingUtil:
    def __init__(self):
        self.logger = logging.getLogger('ClipAI')
        self.logger.setLevel(logging.DEBUG)

        # 创建日志目录
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 按时间命名日志文件
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        log_file = f"{log_dir}/{timestamp}.log"

        # 配置循环文件处理器(10MB限制)
        handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def debug(self, message):
        self.logger.debug(message)

    def info(self, message):
        self.logger.info(message)

    def warn(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)


# 全局日志对象
logger = LoggingUtil()

from rest_framework.response import Response
class ApiResponse(Response):
    """统一响应格式（修复后）"""
    def __init__(self, data=None, message='success', status=200, **kwargs):
        # 确保message是字符串类型
        if not isinstance(message, str):
            # 如果是字典类型（如表单验证错误），转换为字符串
            if isinstance(message, dict):
                # 将字典转换为用分号分隔的键值对字符串
                message = "; ".join([f"{k}: {', '.join(v)}" for k, v in message.items()])
            else:
                # 其他类型强制转换为字符串
                message = str(message)
        # 确保data不为null，如果为null则设为空字典
        if data is None:
            data = {}

        response_data = {
            'code': status,
            'message': message,
            'data': data
        }
        # 始终使用200作为HTTP状态码
        super().__init__(response_data, status=200, **kwargs)

