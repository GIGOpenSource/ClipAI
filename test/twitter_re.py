# test_tweepy_post_and_metrics.py
import tweepy
import time
import os
from datetime import datetime


def create_twitter_client():
    """创建Twitter客户端"""
    api_key = 'j6LGmKd900BffcebIC2LEAMoO'
    api_secret = 'ljIda2o5bCcUJqlXmF4rhRib672A9OOOmd3W5IBQzTLXsGtYbP'
    access_token =  '1757587650905591808-JFyAVeDMS6q72SPEHxH7jMBfnMhGMW'
    access_token_secret = 'DvOqMstuw8xjxasEitHuY7t6OTmv5Ps1KsKog2BcOasuE'
    if not all([api_key, api_secret, access_token, access_token_secret]):
        raise ValueError("请设置Twitter API凭证环境变量")

    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        wait_on_rate_limit=True
    )

    return client


def post_tweet(client, text):
    """发布推文"""
    try:
        response = client.create_tweet(text=text)
        print(f"推文发布成功: {response}")

        # 提取推文ID
        tweet_id = None
        if hasattr(response, 'data') and response.data:
            tweet_id = response.data.get('id')

        return tweet_id
    except Exception as e:
        print(f"发布推文失败: {e}")
        return None


def get_tweet_metrics(client, tweet_id):
    """获取推文指标数据"""
    try:
        print(f"正在获取推文 {tweet_id} 的指标")
        # 使用Tweet.fields获取详细信息
        tweet = client.get_tweet(
            id=tweet_id,
            expansions=['author_id'],
            tweet_fields=['public_metrics', 'created_at', 'context_annotations'],
            user_auth = True
        )
        if tweet and tweet.data:
            public_metrics = tweet.data.public_metrics
            return {
                '浏览量(曝光)': public_metrics.get('impression_count', 0),
                '评论数': public_metrics.get('reply_count', 0),
                '点赞数': public_metrics.get('like_count', 0),
                '转发数': public_metrics.get('retweet_count', 0),
                '引用数': public_metrics.get('quote_count', 0),
                '创建时间': tweet.data.created_at
            }
        else:
            return None

    except Exception as e:
        print(f"获取推文指标失败: {e}")
        return None

def test_authentication(client):
   try:
       me = client.get_me(user_auth=True)
       print(f"认证成功，用户信息: {me.data}")
       return True
   except Exception as e:
       print(f"认证失败: {e}")
       return False


def get_tweet_replies(client, tweet_id):
    """获取推文的评论列表"""
    try:
        # 搜索回复特定推文的推文
        query = f"conversation_id:{tweet_id} is:reply"
        tweets = client.search_recent_tweets(
            query=query,
            tweet_fields=['author_id', 'conversation_id', 'created_at'],
            user_fields=['username', 'name'],
            expansions=['author_id'],
            max_results=10,
            user_auth=True
        )

        if tweets.data:
            replies = []
            users = {user.id: user for user in tweets.includes.get("users", [])} if tweets.includes else {}

            for tweet in tweets.data:
                author = users.get(tweet.author_id, None)
                replies.append({
                    'tweet_id': tweet.id,
                    'text': tweet.text,
                    'author_id': tweet.author_id,
                    'author_username': author.username if author else 'Unknown',
                    'author_name': author.name if author else 'Unknown'
                })

            return replies
        else:
            print("没有找到评论")
            return []

    except Exception as e:
        print(f"获取评论失败: {e}")
        return []


def reply_to_comment(client, comment_id, text):
    """回复特定评论"""
    try:
        response = client.create_tweet(
            text=text,
            in_reply_to_tweet_id=comment_id,
            user_auth=True
        )

        if response.data:
            print(f"回复成功，推文ID: {response.data.get('id')}")
            return response.data.get('id')
        else:
            print("回复失败")
            return None

    except Exception as e:
        print(f"回复评论失败: {e}")
        return None


def reply_good_to_comments(client, target_tweet_id):
    """回复所有评论人'good'"""
    try:
        # 获取评论列表
        comments = get_tweet_replies(client, target_tweet_id)

        if not comments:
            print("没有评论可回复")
            return

        print(f"找到 {len(comments)} 条评论，开始回复...")

        for comment in comments:
            print(f"正在回复用户 @{comment['author_username']} 的评论...")

            # 回复 "good"
            reply_text = f"@{comment['author_username']} super good"
            reply_id = reply_to_comment(client, comment['tweet_id'], reply_text)

            if reply_id:
                print(f"成功回复评论 {comment['tweet_id']}")
            else:
                print(f"回复评论 {comment['tweet_id']} 失败")

            # 避免触发速率限制，添加延迟
            time.sleep(2)

    except Exception as e:
        print(f"批量回复出错: {e}")

def main():
    """主函数"""
    try:
        # 创建Twitter客户端
        client = create_twitter_client()
        time.sleep(5)


        for i in range(5):
            # 发布测试推文
            test_text = f"测试推文发布 16：29  第{i}次  评论点赞 转发 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} #Test @LypResf65149 @liangwater"
            print(f"正在发布推文: {test_text}")

            tweet_id = post_tweet(client, test_text)

            if not tweet_id:
                print("推文发布失败，无法获取推文ID")
                return

            print(f"推文ID: {tweet_id}")

            # 等待一段时间让数据同步
            print("等待10秒让数据同步...")
            time.sleep(10)

            # 获取推文指标
            metrics = get_tweet_metrics(client, tweet_id)
            if metrics:
                print("\n=== 推文指标数据 ===")
                print(f"推文ID: {tweet_id}")
                for key, value in metrics.items():
                    print(f"{key}: {value}")
            else:
                print("无法获取推文指标数据")




    except Exception as e:
        print(f"程序执行出错: {e}")



if __name__ == "__main__":
    main()
