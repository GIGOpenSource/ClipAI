#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：ClipAI
@File    ：runTimingTask.py
@Author  ：LYP
@Date    ：2025/10/10 9:38
@description : 定时任务执行模块
"""
from distutils.log import fatal

import requests
import random
import json
from typing import List, Dict
from datetime import datetime

from ai.models import AIConfig
from social.models import PoolAccount
from tasks.models import SimpleTaskRun
from utils.largeModelUnit import LargeModelUnit
from utils.twitterUnit import TwitterUnit, createTaskDetail
from models.models import TasksSimpletaskrun, TasksSimpletask, SocialPoolaccount, TasksSimpletaskSelectedAccounts
from stats.utils import record_success_run
from utils.utils import generate_message, logger, merge_text


def run_timing_task(task_id):
    """
    执行定时任务
    :param task_id: 任务ID
    """
    try:
        task = TasksSimpletask.objects.get(id=task_id)
        robotList = TasksSimpletaskSelectedAccounts.objects.filter(simpletask_id=task_id).values('poolaccount_id')
        robot_ids = [item["poolaccount_id"] for item in robotList]
        accounts = SocialPoolaccount.objects.filter(id__in=robot_ids)

        for acc in accounts:
            process_account_task(acc, task)

    except Exception as e:
        logger.error(f"执行定时任务失败: {e}")
        raise Exception(f"执行定时任务失败: {str(e)}")


def process_account_task(account, task):
    """处理单个账号的任务执行"""
    # 使用限制检查
    if getattr(account, 'usage_policy', 'unlimited') == 'limited':
        today = datetime.now().date()
        used_today = SimpleTaskRun.objects.filter(account=account, created_at__date=today).count()
        if used_today >= 2:
            logger.info(f"账号 {account.id} 已达每日使用上限")
            return

    cfg = AIConfig.objects.filter(enabled=True).first()
    # AI文本生成
    text, ai_meta = generate_ai_text(task, cfg)
    final_text = merge_text(task, text)
    logger.info(f"为账号 {task.id} 生成的文本：{final_text}")
    # 发布到平台
    if task.provider == 'twitter':
        flags = send_to_twitter(account, task, cfg, final_text)
    return flags

def generate_ai_text(task, cfg):
    """调用AI模型生成文本"""
    global text, flag
    try:
        cli = LargeModelUnit(cfg.model, cfg.api_key, cfg.base_url)
        messages = generate_message(task)
        if cfg.provider == "openai":
            flag, text = cli.generateToOpenAI(messages=messages)
        elif cfg.provider == "deepseek":
            flag, text = cli.generateToDeepSeek(messages=messages)
        else:
            pass
        text = text + "\n" + task.last_text
        logger.info(f"调用模型成功，返回结果：{text}")
        if flag:
            ai_meta = {
                'model': cfg.model,
                'provider': cfg.provider,
                'final_text': text,
                'language': getattr(task, 'language', 'auto'),
            }

            return text, ai_meta
    except Exception as e:
        print(f"调用模型失败：\n:${repr(e)}")
        logger.warn(f"为账号 {task.id} 调用模型失败：{e}")
    return '', {}


def send_to_twitter(account, task, cfg, content):
    """发送推文"""
    try:
        api_key = account.api_key
        api_secret = account.api_secret
        at = account.access_token
        ats = account.access_token_secret
        client = TwitterUnit(api_key, api_secret, at, ats)

        if task.type == 'post':
            flags, resp = client.sendTwitter(content, int(account.id), task, cfg, userId=task.owner_id)
            logger.info(f"推文发送成功响应: {resp}")
            try:
                record_success_run(
                    owner_id=task.owner_id,
                    provider='twitter',
                    task_type=task.type,
                    started_date=datetime.now().date()
                )
            except Exception as e:
                logger.warn(f"记录运行状态失败: {e}")
            return flags
    except Exception as e:
        logger.error(f"发送推文失败: {e}")
        raise Exception(f"发送推文失败: {str(e)}")
