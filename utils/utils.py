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
        handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
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
