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
from utils.largeModelUnit import LargeModelUnit
from utils.twitterUnit import TwitterUnit, createTaskDetail
from models.models import TasksSimpletaskrun
from stats.utils import record_success_run
from utils.utils import generate_message


def genrate_text(task, prompt_config: Dict, robot_objects: List) -> str:
    """
    根据配置信息和机器人对象生成文本

    :param task: 任务对象
    :param prompt_config: 提示词配置信息，包含模型参数等
    :param robot_objects: 机器人对象列表
    :return: 生成的文本
    """
    # 从配置中提取参数
    model = prompt_config.get("model", "gpt-3.5-turbo-instruct")
    temperature = prompt_config.get("temperature", 0.9)
    max_tokens = prompt_config.get("max_tokens", 1024)
    api_key = prompt_config.get("api_key", "")
    base_url = prompt_config.get("base_url", "")
    # 创建大模型客户端
    cli = LargeModelUnit(model, api_key, base_url, temperature)
    # 构造提示词消息
    messages = construct_messages(task, prompt_config, robot_objects)
    # 根据模型类型调用相应的方法
    if "deepseek" in model.lower():
        success, text = cli.generateToDeepSeek(messages)
    else:
        success, text = cli.generateToOpenAI(messages)

    if success:
        return text
    else:
        raise Exception("Failed to generate text using large model")


def construct_messages(task, prompt_config, robot_objects):
    """
    构造发送给大模型的消息
    :param task: 任务对象
    :param prompt_config: 提示词配置
    :param robot_objects: 机器人对象列表
    :return: 消息列表
    """
    messages = []
    # 添加系统角色提示
    system_prompt = prompt_config.get("system_prompt", "You are a helpful assistant.")
    messages.append({"role": "system", "content": system_prompt})
    # 添加用户提示词
    user_prompt = prompt_config.get("user_prompt", "Please generate content.")
    messages.append({"role": "user", "content": user_prompt})
    return messages


def run_timing_task(task, validated_data: Dict, prompt_config: Dict, robot_objects: List):
    """
    执行定时任务

    :param task: 任务对象
    :param validated_data: 任务配置数据，包含mentions, tags等参数
    :param prompt_config: 提示词配置
    :param robot_objects: 机器人对象列表
    """
    # 生成AI文本
    try:
        # 中英文提示词
        message = generate_message(task)

        LargeModelUnit()

    except Exception as e:
        raise Exception(f"生成文本失败: {str(e)}")

    # 处理任务参数
    user_text = (validated_data.get("text") or '').strip()
    lang_code = (validated_data.get("language") or 'auto')
    task_type = validated_data.get("type")
    provider = validated_data.get("provider")
    tags = validated_data.get("tags", [])
    mentions = validated_data.get("mentions", [])

    # 语言映射
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
    lang_name = lang_map.get(lang_code, 'Auto')

    # 构造最终文本
    final_text = generated_text
    if user_text:
        final_text = f"{final_text} {user_text}"

    # 添加标签
    if tags:
        tail = ' ' + ' '.join('#' + t.lstrip('#') for t in tags[:5])
        final_text = (final_text + tail).strip()

    # 添加提及
    if mentions:
        mention_list = []
        if isinstance(mentions, str):
            mention_list = [m.strip() for m in mentions.split(',') if m.strip()]
        elif isinstance(mentions, list):
            mention_list = [str(m).strip() for m in mentions if str(m).strip()]

        if mention_list:
            mstr = ' ' + ' '.join('@' + m.lstrip('@') for m in mention_list[:10])
            final_text = (final_text + mstr).strip()

    # 为每个机器人对象执行发帖操作
    results = []
    for robot in robot_objects:
        try:
            # 获取机器人账户信息
            api_key = getattr(robot, 'api_key', '')
            api_secret = getattr(robot, 'api_secret', '')

            if provider == 'twitter':
                # 执行Twitter发帖
                at = robot.get_access_token()
                ats = robot.get_access_token_secret()
                client = TwitterUnit(api_key, api_secret, at, ats)

                if task_type == 'post':
                    flag, resp = client.sendTwitter(
                        final_text,
                        int(robot.id),
                        validated_data,
                        prompt_config,
                        userId=validated_data.get("owner_id", 0)
                    )

                    if flag:
                        tweet_id = resp["id"]
                        results.append({
                            'account_id': robot.id,
                            'status': 'ok',
                            'tweet_id': tweet_id
                        })

                        # 记录成功运行
                        try:
                            record_success_run(
                                owner_id=validated_data.get("owner_id", 0),
                                provider='twitter',
                                task_type=task_type,
                                started_date=timezone.now().date()
                            )
                        except Exception:
                            pass
                    else:
                        results.append({
                            'account_id': robot.id,
                            'status': 'error',
                            'error': '发送失败'
                        })

        except Exception as e:
            results.append({
                'account_id': robot.id,
                'status': 'error',
                'error': str(e)
            })

    return results
