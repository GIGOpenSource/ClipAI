#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：ClipAI 
@File    ：twitterUnit.py
@Author  ：LYP
@Date    ：2025/10/10 15:21 
@description : 推特工具类
"""
import time
from http.client import responses

from tweepy import Client
from utils.utils import LoggingUtil

logger = LoggingUtil()


class TwitterUnit(object):
    def __init__(self, api_key: str, api_secret: str, access_token: str, access_token_secret: str):
        """
        :param api_key:api_key
        :param api_secret:api_secret
        :param access_token:access_token
        :param access_token_secret:access_token_secret
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.client = Client(
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret,
            wait_on_rate_limit=True
        )

    def sendTwitter(self, text: str) -> tuple[bool, dict | None]:
        """
        发布推文
        :param text: 待发送推文消息体
        :return:
        """
        try:
            response = self.client.create_tweet(text=text)
            logger.info(f"推文发布成功: {response}")
            try:
                if hasattr(response, 'data') and response.data:
                    data = response.data
                else:
                    data = dict()
            except:
                data = dict()
            return True, data
        except Exception as e:
            logger.error(f"发布推文失败: {e}")
            return False, None

    def getTwitterData(self, tweet_id: str) -> tuple[bool, dict | None]:
        """
        获取推文指标数据以及评论列表
        :param tweet_id:推文文章ID
        :return:
        """
        logger.info(f"正在获取推文 {tweet_id} 的指标")
        response = self.client.get_tweet(id=tweet_id, expansions=['author_id'],
                                         tweet_fields=['public_metrics', 'created_at', 'context_annotations'],
                                         user_auth=True)
        commentResponse = self.client.search_recent_tweets(
            query=f"conversation_id:{tweet_id} is:reply",
            tweet_fields=['author_id', 'conversation_id', 'created_at'],
            user_fields=['username', 'name'],
            expansions=['author_id'],
            max_results=10,
            user_auth=True
        )
        try:
            try:
                if hasattr(response, 'data') and response.data.public_metrics:
                    result = response.data.public_metrics
                    data = {
                        'pageViews': result.get('impression_count', 0),  # 浏览量(曝光)
                        'commentCount': result.get('reply_count', 0),  # 评论数
                        'likeCount': result.get('like_count', 0),  # 点赞数
                        'repostCount': result.get('retweet_count', 0),  # 转发数
                        'citationCount': result.get('quote_count', 0),  # 引用数
                        'createDate': response.data.created_at  # 创建时间
                    }
                else:
                    data = dict()
                if hasattr(commentResponse, 'data') and commentResponse.data:
                    data['comments'] = [
                        {"id": item.id, "text": item.text, "author_id": item.author_id, "created_at": item.created_at}
                        for item in commentResponse.data]
                else:
                    data['comments'] = []
            except:
                data = dict()
            return True, data
        except Exception as e:
            logger.error(f"获取推文 {tweet_id} 指标数据失败: {e}")
            return False, None

    def replyTwitterMessages(self, tweet_id: str, text: str) -> bool:
        """
        回复特定评论
        :param tweet_id: 评论ID
        :param text: 回复内容
        :return:
        """
        try:
            responses = self.client.create_tweet(
                text=text,
                in_reply_to_tweet_id=tweet_id,
                user_auth=True
            )
            if responses.data:
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"回复指定推文{tweet_id} 失败: {e}")
            return False


if __name__ == '__main__':
    api_key = '48HHyhw92FV9hwp2JfM2VpjJ6'
    api_secret = 'GPwBw3p5t7O2ryUNdbWUpc0ROjrRjbceWSYLDj1tIXxXe7XD9M'
    access_token = '1757141001687511040-ITIEcDJ5OSF1Jksnk4kSHMJALVX3L5'
    access_token_secret = 'ENxoQtZpI6gSEgEtu4Vdz7fDBNOXJ1zYv1YftZCdeGXEz'
    client = TwitterUnit(api_key, api_secret, access_token, access_token_secret)
    client.sendTwitter("测试")
