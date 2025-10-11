from datetime import datetime, timedelta

from tasks.models import TArticle as Article
from social.models import PoolAccount
from utils.twitterUnit import TwitterUnit

class TimeoutError(Exception):
    pass

# 超时处理函数
def timeout_handler(signum, frame):
    raise TimeoutError("API调用超时")

def collect_recent_articles_data():
    """
    统计10天内的文章数据，获取文章ID和机器人ID，
    然后调用Twitter API获取详细数据
    """
    # 计算10天前的日期
    s1 = str(datetime.now() - timedelta(days=10))[:10] + " 00:00:00"
    s2 = str(datetime.now() + timedelta(days=1))[:10] + " 00:00:00"

    # 查询10天内的文章数据
    recent_articles = Article.objects.filter(created_at__range=[s1, s2]).values('article_id', 'robot_id')

    # 创建结果列表
    results = []
    #
    # 遍历文章数据
    for article_data in recent_articles:
        article_id = article_data['article_id']
        robot_id = article_data['robot_id']
        print(article_id, robot_id)

        try:
            # 根据robot_id获取对应的API凭证
            pool_account = PoolAccount.objects.get(id=robot_id)

            # 初始化Twitter客户端
            twitter_client = TwitterUnit(
                api_key=pool_account.api_key,
                api_secret=pool_account.api_secret,
                access_token=pool_account.access_token,
                access_token_secret=pool_account.access_token_secret
            )
            try:
                # 调用getTwitterData方法获取推文详细数据
                success, twitter_data = twitter_client.getTwitterData(article_id)

                if success and twitter_data:
                    # 存储结果
                    results.append({
                        'article_id': article_id,
                        'robot_id': robot_id,
                        'twitter_data': twitter_data
                    })
                    # 这里可以更新数据库中的文章统计数据
                    update_article_stats(article_id, twitter_data)
                else:
                    continue
            except TimeoutError:
                print(f"处理article_id {article_id}超时，跳过")
                continue
            except Exception as e:
                # 检查是否为速率限制错误
                if "Rate limit exceeded" in str(e):
                    print(f"遇到速率限制，跳过article_id {article_id}")
                    continue
            else:
                print(f"处理article_id {article_id}成功")
        except PoolAccount.DoesNotExist:
            print(f"未找到robot_id为{robot_id}的账号信息")
            continue
        except Exception as e:
            print(f"处理article_id {article_id}时出错: {e}")
            continue
    return results


def update_article_stats(article_id, twitter_data):
    """
    更新文章统计数据
    """
    try:
        article = Article.objects.get(article_id=article_id)
        article.impression_count = twitter_data.get('pageViews', 0)
        article.comment_count = twitter_data.get('commentCount', 0)
        article.like_count = twitter_data.get('likeCount', 0)
        article.updated_at = datetime.now()

        # 更新其他需要的字段
        article.save()

    except Article.DoesNotExist:
        print(f"未找到article_id为{article_id}的文章")
    except Exception as e:
        print(f"更新文章统计数据时出错: {e}")


# if __name__ == '__main__':
#     results = collect_recent_articles_data()
#     print(results)