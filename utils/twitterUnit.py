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
from datetime import datetime
from math import trunc

from tweepy import Client
from tasks.models import TArticle as Article, TArticleComments as ArticleComments
from django.db import transaction


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
            wait_on_rate_limit=False
        )

    def sendTwitter(self, text: str, robotId: int) -> tuple[bool, dict | None]:
        """
        发布推文
        :param text: 待发送推文消息体
        :param robotId: 机器人ID
        :return:
        """
        try:
            response = self.client.create_tweet(text=text)
            # logger.info(f"推文发布成功: {response}")
            try:
                if hasattr(response, 'data') and response.data:
                    data = response.data
                    createArticle("x", data, robotId)
                else:
                    data = dict()
            except:
                data = dict()
            return True, data
        except Exception as e:
            # logger.error(f"发布推文失败: {e}")
            return False, None

    def getTwitterData(self, tweet_id: str) -> tuple[bool, dict | None]:
        """
        获取推文指标数据以及评论列表
        :param tweet_id:推文文章ID
        :return:
        """
        try:
            # logger.info(f"正在获取推文 {tweet_id} 的指标")
            response = self.client.get_tweet(id=tweet_id, expansions=['author_id'],
                                             tweet_fields=['public_metrics', 'created_at', 'context_annotations'],
                                             user_auth=True)
            if hasattr(response, 'headers'):
                remaining = response.headers.get('x-rate-limit-remaining')
                reset_time = response.headers.get('x-rate-limit-reset')

                # 如果剩余请求数很少，可以选择跳过
                if remaining is not None and int(remaining) < 2:
                    raise Exception("Rate limit exceeded")

            commentResponse = self.client.search_recent_tweets(
                query=f"conversation_id:{tweet_id} is:reply",
                tweet_fields=['author_id', 'conversation_id', 'created_at'],
                user_fields=['username', 'name'],
                expansions=['author_id'],
                max_results=10,
                user_auth=True
            )
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
                    updateArticle(tweet_id, data)
                else:
                    data = dict()
                if hasattr(commentResponse, 'data') and commentResponse.data:
                    userList = [{"id": str(item.id), "name": item["data"]["name"], "username": item["data"]["username"]}
                                for
                                item in commentResponse.includes["users"]]
                    comments = [{"id": str(item.id), "text": item.text, "author_id": item.author_id,
                                 "created_at": item.created_at}
                                for item in commentResponse.data]
                    user_dict = {user['id']: user for user in userList}
                    newComments = [{**item, 'name': user_dict.get(item['author_id'], {}).get('name', 'Unknown'),
                                    'username': user_dict.get(item['author_id'], {}).get('username', 'unknown_user')}
                                   for item in
                                   comments]
                    data['comments'] = newComments
                    createArticleComments(tweet_id, newComments)
                else:
                    data['comments'] = []
            except:
                data = dict()
            return True, data
        except Exception as e:
            # logger.error(f"获取推文 {tweet_id} 指标数据失败: {e}")
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
            # logger.error(f"回复指定推文{tweet_id} 失败: {e}")
            return False


@transaction.atomic
def createArticle(platform: str, result: dict, robotId: int) -> Article:
    """
    :param platform:平台名
    :param robotId
    :param result:发送成功返回内容 {'edit_history_tweet_ids': ['1976839557380554887'], 'id': '1976839557380554887', 'text': '测试'}
    """
    article_id = result.get('id')
    article_text = result.get('text')
    if not Article.objects.filter(id=article_id, platform=platform).exists():
        article = Article.objects.create(
            article_id=article_id,
            platform=platform,
            article_text=article_text,
            impression_count=0,
            comment_count=0,
            message_count=0,
            like_count=0,
            click_count=0,
            robot_id=robotId,
            created_at=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        )
        return article


@transaction.atomic
def updateArticle(articleId: str, data: dict) -> tuple[bool, Article | None]:
    """
    回复特定评论
   :param articleId: 文章ID
   :param data: 获取到的文章数据 点赞量等
   data = {
            'pageViews': result.get('impression_count', 0),  # 浏览量(曝光)
            'commentCount': result.get('reply_count', 0),  # 评论数
            'likeCount': result.get('like_count', 0),  # 点赞数
            'repostCount': result.get('retweet_count', 0),  # 转发数
            'citationCount': result.get('quote_count', 0),  # 引用数
            'createDate': response.data.created_at  # 创建时间
        }
   :return:
   """
    try:
        article = Article.objects.get(article_id=articleId)
        article.impression_count = data.get("pageViews", 0)
        article.comment_count = data.get("commentCount", 0)
        article.like_count = data.get("likeCount", 0)
        article.updated_at = datetime.now()
        article.save()
        return True, article
    except Article.DoesNotExist:
        return False, None


@transaction.atomic
def createArticleComments(articleId: str, data: list) -> bool:
    """
    更新文章评论
    :param articleId: 文章ID
    :param data: 获取到的文章数据 点赞量等
    {'author_id': 1751080672184487936,
     'created_at': datetime.datetime(2025, 10, 11, 9, 31, 5, tzinfo=datetime.timezone.utc),
     'id': 1976943626854044122, 'name': 'Katharyn Jeanie',
    'text': '@liangwater @AustinJuli67152 第二个人评论第二条帖子 的第一个人第一次',
    'username': 'KatharynJe68272'}
    """
    try:
        for item in data:
            comment = ArticleComments.objects.create(
                article_id=articleId,
                comment_id=item.get("id"),
                content=item.get("text"),
                commenter_id=item.get("author_id"),
                created_at=item.get("created_at"),
                commenter_nickname=item.get("name")
            )
            comment.save()
        return True
    except:
        return False
