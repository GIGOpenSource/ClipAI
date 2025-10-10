import tweepy
import time
from datetime import datetime




def create_twitter_client():
    """创建Twitter客户端"""
    api_key = 'Tive2BlUTyy6J60ZgOAQ2cikK'
    api_secret = 'X2DvWeboT732qddqGrGQ5ftsJ49ybMEIX0st7naGE08hyz51w1'
    access_token = '1757283066005827584-hbKjQlyiFXDI8OWlSb5IuX2VqXd0ft'
    access_token_secret = 'OiRP5nsRAV62IkWGiF6wMzAtsZcnfLVzHK9WaSyA52NAH'

    if not all([api_key, api_secret, access_token, access_token_secret]):
        raise ValueError("请设置Twitter API凭证环境变量")

    # 创建支持 API v1.1 的客户端
    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        wait_on_rate_limit=True
    )

    # 同时创建 API v1.1 的认证对象
    auth = tweepy.OAuth1UserHandler(
        api_key, api_secret, access_token, access_token_secret
    )
    api_v1 = tweepy.API(auth)

    return client, api_v1


def get_direct_messages(api_v1):
    """获取私信列表"""
    try:
        # 使用 API v1.1 获取私信
        messages = api_v1.get_direct_messages(count=10)

        dm_list = []
        for dm in messages:
            dm_list.append({
                'id': dm.id,
                'text': dm.message_create['message_data']['text'],
                'sender_id': dm.message_create['sender_id'],
                'recipient_id': dm.message_create['target']['recipient_id'],
                'created_at': dm.created_timestamp
            })

        return dm_list
    except Exception as e:
        print(f"获取私信失败: {e}")
        return []


def send_direct_message(api_v1, recipient_id, text):
    """发送私信"""
    try:
        # 使用 API v1.1 发送私信
        dm = api_v1.send_direct_message(recipient_id=recipient_id, text=text)
        print(f"私信发送成功，ID: {dm.id}")
        return dm.id
    except Exception as e:
        print(f"发送私信失败: {e}")
        return None


def process_direct_messages():
    """处理私信：获取并回复"""
    try:
        # 创建客户端
        client, api_v1 = create_twitter_client()

        # 获取私信
        messages = get_direct_messages(api_v1)

        if not messages:
            print("没有收到私信")
            return

        print(f"获取到 {len(messages)} 条私信")

        # 处理每条私信并回复
        for msg in messages:
            print(f"\n私信内容: {msg['text']}")
            print(f"发送者ID: {msg['sender_id']}")

            # 回复 "hello man"
            reply_text = "hello man"
            send_direct_message(api_v1, msg['sender_id'], reply_text)

            # 避免触发速率限制
            time.sleep(1)

    except Exception as e:
        print(f"处理私信时出错: {e}")


# 在 main 函数中调用
def main():
    """主函数"""
    try:
        # 创建Twitter客户端
        client, api_v1 = create_twitter_client()
        time.sleep(5)

        tweet_id = 1976537965280231623
        # 获取推文指标
        from test.twitter_re import get_tweet_metrics
        metrics = get_tweet_metrics(client, tweet_id)

        if metrics:
            print("\n=== 推文指标数据 ===")
            print(f"推文ID: {tweet_id}")
            for key, value in metrics.items():
                print(f"{key}: {value}")
        else:
            print("无法获取推文指标数据")

        # 处理私信
        print("\n=== 处理私信 ===")
        process_direct_messages()

    except Exception as e:
        print(f"程序执行出错: {e}")
if __name__ == "__main__":
    main()
