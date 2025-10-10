# 修正后的 twitter_test.py
import tweepy

# 创建模拟的对象
class MockAccount:
    def __init__(self):
        self.api_key = 'Tive2BlUTyy6J60ZgOAQ2cikK'
        self.api_secret = 'X2DvWeboT732qddqGrGQ5ftsJ49ybMEIX0st7naGE08hyz51w1'
        # 注意：这里应该是 get_access_token() 和 get_access_token_secret() 方法
        # 但现在直接使用字符串值进行测试


class MockTask:
    def __init__(self):
        self.provider = 'twitter'
        self.type = 'post'  # 添加这行，原始代码中缺失


# 创建实例
acc = MockAccount()
task = MockTask()
text = 'Hello ~，#hello @GRebbeca56543 @EttieMarit46549'


def test_twitter_post():
    try:
        # 官方库 Tweepy，使用 OAuth1.0a
        api_key = acc.api_key
        api_secret = acc.api_secret
        at = '1757283066005827584-hbKjQlyiFXDI8OWlSb5IuX2VqXd0ft'  # 直接使用字符串
        ats = 'OiRP5nsRAV62IkWGiF6wMzAtsZcnfLVzHK9WaSyA52NAH'  # 直接使用字符串

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=at,
            access_token_secret=ats
        )

        if task.type == 'post':
            print(f"正在发送推文: {text}")
            resp = client.create_tweet(text=text)
            print("推文发送成功!")
            print(f"响应: {resp}")
            # 提取 tweet ID
            tweet_id = None
            try:
                data = getattr(resp, 'data', None) or {}
                tweet_id = data.get('id') if isinstance(data, dict) else getattr(data, 'id', None)
                print(f"Tweet ID: {tweet_id}")
            except Exception as e:
                print(f"提取 tweet ID 时出错: {e}")
            return True

    except tweepy.Unauthorized as e:
        print("401 认证失败 - 请检查您的 API 凭据:")
        print(f"- Consumer Key: {api_key}")
        print(f"- Consumer Secret: {api_secret}")
        print(f"- Access Token: {at}")
        print(f"- Access Token Secret: {ats}")
        print(f"详细错误: {e}")
        return False
    except Exception as e:
        print(f"其他错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=== Twitter API 测试 ===")
    test_twitter_post()
