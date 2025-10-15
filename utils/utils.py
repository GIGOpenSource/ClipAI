from typing import List, Dict
from django.core.paginator import EmptyPage
from rest_framework.pagination import PageNumberPagination
import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from rest_framework.response import Response
from models.models import TasksSimpletask as Task

lang_map = {
    'auto': 'Auto',
    'zh': 'Chinese',
    'en': 'English',
    'ja': 'Japanese',
    'ko': 'Korean',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
}


def generate_message(task: Task) -> List[Dict[str, str]]:
    lang_name = lang_map.get(task.language, 'Auto')
    if task.language == "zh" or task.language == "auto":
        base_sys = (getattr(task.prompt, 'content', None) or '你是一个社交媒体助理，请生成简短中文内容。')
        messages = [
            {'role': 'system', 'content': base_sys},
            {'role': 'user',
             'content': f"请生成适合 {task.provider} 的{'回复评论' if task.type == 'reply_comment' else '发帖'}文案。"},
        ]
    elif task.language == "en":
        base_sys = 'You are a social media copywriter. Generate concise, safe English content suitable for Twitter.'
        messages = [
            {'role': 'system', 'content': base_sys},
            {'role': 'system',
             'content': 'Target language: English. Reply ONLY in English. Keep it short and friendly.'},
            {'role': 'user', 'content': f"Please write a short post for {task.provider}."},
        ]
    else:
        base_sys = f'You are a social media copywriter. Generate concise, safe {lang_name} content suitable for Twitter.'
        messages = [
            {'role': 'system', 'content': base_sys},
            {'role': 'system',
             'content': f"Target language: {lang_name}. Reply ONLY in {lang_name}. Keep it short and friendly."},
            {'role': 'user', 'content': f"Please write a short post for {task.provider}."},
        ]
    return messages


def merge_text(task: Task, text: str) -> str:
    """

    :param task:
    :param text:
    :return:
    """
    final_text = text
    if task.tags:
        tail = ' ' + ' '.join('#' + t.lstrip('#') for t in task.tags[:5])
        final_text = (final_text + tail).strip()
    if task.mentions:
        # 处理 mentions：支持字符串和列表格式
        mention_list = []
        if isinstance(task.mentions, str):
            # 字符串格式：'user1,user2,user3'
            mention_list = [m.strip() for m in task.mentions.split(',') if m.strip()]
        elif isinstance(task.mentions, list):
            # 列表格式：['user1', 'user2', 'user3']
            mention_list = [str(m).strip() for m in task.mentions if str(m).strip()]
        # 添加 @ 符号前缀并限制数量
        if mention_list:
            mstr = ' ' + ' '.join('@' + m.lstrip('@') for m in mention_list[:10])
            final_text = (final_text + mstr).strip()
    return final_text


class LoggingUtil:
    def __init__(self):
        self.logger = logging.getLogger('ClipAI')
        self.logger.setLevel(logging.DEBUG)

        # 创建日志目录
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 使用时间轮转日志处理器
        log_file = f"{log_dir}/clipai.log"
        # 每10分钟轮转一次
        handler = TimedRotatingFileHandler(
            log_file,
            when='M',
            interval=10,
            backupCount=100,
            encoding='utf-8'
        )
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


class CustomPagination(PageNumberPagination):
    page_size = 20  # 默认每页条数
    page_query_param = 'currentPage'  # 关键：匹配前端的 "currentPage" 参数（指定页码）
    page_size_query_param = 'pageSize'  # 匹配前端的 "pageSize" 参数（指定每页条数）
    max_page_size = 999  # 最大每页条数限制

    def get_paginated_response(self, data):
        # 现在这个方法会在分页生效时被自动调用
        return ApiResponse({
            'pagination': {
                'page': self.page.number,  # 当前页码
                'page_size': self.page.paginator.per_page,  # 使用实际的page_size参数
                'total': self.page.paginator.count,  # 总记录数
                'total_pages': self.page.paginator.num_pages  # 总页数
            },
            'results': data
        })

    def paginate_queryset(self, queryset, request, view=None):
        """
        处理超出范围的页码请求
        """
        try:
            return super().paginate_queryset(queryset, request, view=view)
        except Exception as e:
            # 捕获所有分页相关的异常
            if "Invalid page" in str(e) or isinstance(e, EmptyPage):
                # 当请求的页码无效时，返回空结果而不是抛出异常
                self.request = request
                # 创建一个空的分页结果
                page_size = self.get_page_size(request) or self.page_size
                from django.core.paginator import Paginator
                empty_paginator = Paginator([], page_size)
                self.page = empty_paginator.page(1)
                return []
            # 如果是其他异常，重新抛出
            raise e


# 全局日志对象
logger = LoggingUtil()
