#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：ClipAI 
@File    ：largeModelUnit.py
@Author  ：LYP
@Date    ：2025/10/10 9:38
@description : 大模型生成返回词
"""
import requests
import random
import json
from typing import List, Dict


class LargeModelUnit(object):
    def __init__(self, model: str, api_key: str, base_url: str, temperature: float = 0.7):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.payload = {"model": self.model, "temperature": random.uniform(temperature, 2), "top_p": 0.9,
                        "presence_penalty": 0.5}
        self.headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
                        'Authorization': f'Bearer {self.api_key}'}

    def generateToOpenAI(self, messages: List[Dict[str, str]]) -> tuple[int, str]:
        """
        千问生成提示词
        :param messages:
        :return:
        """
        self.payload["messages"] = messages
        resp = requests.post(self.base_url, json=self.payload, headers=self.headers).json()
        try:
            return True, resp["choices"][0]["message"]["content"]
        except:
            return False, ""

    def generateToDeepSeek(self, messages: List[Dict[str, str]]) -> tuple[int, str]:
        """
        DeepSeek生成提示词
        :param messages:
        :return:
        """
        self.payload["messages"] = messages
        resp = requests.post(self.base_url, data=json.dumps(self.payload), headers=self.headers).json()

        try:
            return True, resp["choices"][0]["message"]["content"]
        except:
            return False, ""


if __name__ == '__main__':
    base_url = "https://api.deepseek.com/chat/completions"
    model = "deepseek-chat"
    api_key = "sk-7fbfac05d6314d779d70da5702583576"
    base_sys = 'You are a social media copywriter. Generate concise, safe English content suitable for Twitter.'
    messages = [
        {'role': 'system', 'content': base_sys},
        {'role': 'system',
         'content': 'Target language: English. Reply ONLY in English. Keep it short and friendly.'},
        {'role': 'user', 'content': f"Please write a short post for deepseek."},
    ]
    client = LargeModelUnit(model, api_key, base_url)
    flag,message  = client.generateToDeepSeek( messages)
    print(message)