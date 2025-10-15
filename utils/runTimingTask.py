#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：ClipAI
@File    ：largeModelUnit.py
@Author  ：LYP
@Date    ：2025/10/10 9:38
@description : 大模型生成返回词
"""
from utils.utils import logger
from models.models import AiAiconfig as Ai, SocialPoolaccount as Social, TasksSimpletask as Task
from utils.largeModelUnit import LargeModelUnit
from utils.twitterUnit import TwitterUnit


def generate_text(task: Task, ai: Ai, social: Social):
    """
    :param task: 任务
    :param ai: ai配置
    :param social: 机器人
    :return:
    """
    try:
        robot = LargeModelUnit(ai.model, ai.api_key, ai.base_url)
    except Exception as e:
        print(e)
        logger.error(f"generate_text生成失败：\n{e}")
