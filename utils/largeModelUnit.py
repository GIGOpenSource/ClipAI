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
from typing import List, Optional, Dict, Any


class LargeModelUnit(object):
    def __init__(self, model: str, api_key: str, base_url: str, temperature: float = 0.7):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.payload = {"model": self.model, "temperature": random.uniform(temperature, 2)}
        self.headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
                        'Authorization': f'Bearer {self.api_key}'}

    def generateToOpenAI(self, messages: List[Dict[str, str]]) -> tuple[int, str]:
        """
        千问生成提示词
        :param messages:
        :return:
        """
        self.payload["messages"] = messages
        self.payload["top_p "] = 0.9
        self.payload["presence_penalty"] = 0.5
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json', }
        resp = requests.post(self.base_url, json=self.payload, headers=self.headers).json()
        try:
            return True, resp["choices"][0]["message"]["content"]
        except:
            return False, ""

    def generateToDeepSeek(self, messages: str) -> tuple[int, str]:
        """
        DeepSeek生成提示词
        :param messages:
        :return:
        """
        self.payload["prompt"] = messages
        self.payload["top_p "] = 0.9
        self.payload["presence_penalty"] = 0.5

        resp = requests.post(self.base_url, data=json.dumps(self.payload), headers=self.headers).json()

        try:
            return True, resp["choices"][0]["text"]
        except:
            return False, ""
