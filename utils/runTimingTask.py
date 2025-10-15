#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：ClipAI
@File    ：runTimingTask.py
@Author  ：LYP
@Date    ：2025/10/10 9:38
@description : 定时任务执行模块
"""
import requests
import random
import json
from typing import List, Dict
from datetime import timezone

from ai.models import AIConfig
from social.models import PoolAccount
from tasks.models import SimpleTaskRun
from utils.largeModelUnit import LargeModelUnit
from utils.twitterUnit import TwitterUnit, createTaskDetail
from models.models import TasksSimpletaskrun, TasksSimpletask, SocialPoolaccount
from stats.utils import record_success_run
from utils.utils import generate_message, logger, merge_text

def run_timing_task(task_id, validated_data):
    """
    执行定时任务

    :param task: 任务对象
    :param validated_data: 任务配置数据，包含mentions, tags等参数
    :param prompt_config: 提示词配置
    :param robot_objects: 机器人对象列表ll
    """
    # 生成AI文本
    try:
        task = TasksSimpletask.objects.filter(id=task_id)
        datas = SocialPoolaccount.objects.filter(provider=validated_data["provider"],
                                                 status="active")
        # 中英文提示词
        message = generate_message(task)
        for acc in datas:
            user_text = (task.text or '').strip()
            text = ''
            ai_meta = {}
            last_err = None
            # 每日使用上限：limited 账号每天最多使用 2 次（无论成功与否）
            try:
                if getattr(acc, 'usage_policy', 'unlimited') == 'limited':
                    today = timezone.now().date()
                    used_today = SimpleTaskRun.objects.filter(account=acc, created_at__date=today).count()
            except Exception:
                pass
            should_generate_content = True  # 或者根据具体条件判断
            ai_qs = AIConfig.objects.filter(enabled=True).order_by('-priority', 'name')
            if should_generate_content:
                for cfg in ai_qs:
                    try:
                        cli = LargeModelUnit(cfg.model, cfg.api_key, cfg.base_url)
                        messages = generate_message(task)
                        if user_text:
                            messages.append({'role': 'user', 'content': f"补充上下文：{user_text}"})
                        logger.info(f"为账号 {acc.id} 调用 chat_completion")
                        if cfg.provider == "openai":
                            flag, text = cli.generateToOpenAI(messages=messages)
                        if cfg.provider == "deepseek":
                            flag, text = cli.generateToDeepSeek(messages=messages)
                        if flag:
                            ai_meta = {
                                'model': cfg.model,
                                'provider': cfg.provider,
                                # 'latency_ms': res.get('latency_ms'),
                                # 'tokens': res.get('tokens'),
                                # 'used_prompt': getattr(task.prompt, 'name', None),
                                'final_text': text,
                                'language': getattr(task, 'language', 'auto'),
                            }
                            break
                    except Exception as e:
                        last_err = str(e)
                        logger.info(f"为账号 {acc.id} 调用模型失败：{last_err}")

            # 如果没有生成文本但有用户文本，使用用户文本
            if not text and user_text:
                text = user_text
                ai_meta = {
                    'model': 'user_provided',
                    'provider': 'user',
                    # 'latency_ms': 0,
                    # 'tokens': 0,
                    # 'used_prompt': None,
                    'final_text': text,
                    'language': getattr(task, 'language', 'auto'),
                }
            # 附加 tags/mentions（mentions 前缀 @）
            final_text = text  # 使用为当前账号生成的文本
            logger.info(f"为账号 {acc.id} 生成的文本：{final_text}")
            final_text = merge_text(task, final_text)
            try:
                if task.provider == 'twitter':
                    api_key = acc.api_key
                    api_secret = acc.api_secret
                    at = acc.get_access_token()
                    ats = acc.get_access_token_secret()
                    client = TwitterUnit(api_key, api_secret, at, ats)
                    if task.type == 'post':
                        flag, resp = client.sendTwitter(final_text, int(acc.id), task, cfg, userId=task.owner_id)
                        logger.info(f"推文发送成功响应: {resp}")
                        try:
                            record_success_run(owner_id=task.owner_id, provider='twitter', task_type=task.type,
                                               started_date=timezone.now().date())
                        except Exception as e:
                            pass
            except Exception as e:
                raise Exception(f"生成文本失败: {str(e)}")
    except Exception as e:
        raise Exception(f"生成文本失败: {str(e)}")



