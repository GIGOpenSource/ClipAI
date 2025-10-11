from datetime import timedelta
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
import csv
from drf_spectacular.utils import extend_schema

from utils.utils import logger
from .models import DailyStat
from .serializers import SummaryResponseSerializer


class SummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='统计概览（仅昨天当前用户）', tags=['数据统计'], responses=SummaryResponseSerializer)
    def get(self, request):
        if not (request.user and request.user.is_authenticated):
            return Response({'total_runs': 0, 'succeeded': 0, 'failed': 0, 'success_rate': 0, 'avg_duration_ms': 0, 'sla_met_rate': None})
        yesterday = timezone.now().date() - timedelta(days=1)
        stat = DailyStat.objects.filter(date=yesterday, owner_id=request.user.id).first()
        post = getattr(stat, 'post_count', 0) if stat else 0
        r_c = getattr(stat, 'reply_comment_count', 0) if stat else 0
        r_m = getattr(stat, 'reply_message_count', 0) if stat else 0
        total = int(post) + int(r_c) + int(r_m)
        return Response({
            'total_runs': total,
            'succeeded': total,
            'failed': 0,
            'success_rate': 1 if total else 0,
            'avg_duration_ms': 0,
            'sla_met_rate': None,
        })


class OverviewView(APIView):
    permission_classes = [IsAuthenticated]
    @extend_schema(summary='昨日统计明细（当前用户，单日一行）', tags=['数据统计'])
    def get(self, request):
        if not (request.user and request.user.is_authenticated):
            return Response({'results': []})
        yesterday = (timezone.now().date() - timedelta(days=1))
        stats_qs = DailyStat.objects.filter(date=yesterday, owner_id=request.user.id)
        data = list(stats_qs.values(
            'date', 'account_count', 'ins', 'x', 'fb', 'post_count',
            'reply_comment_count', 'reply_message_count', 'total_impressions'
        ).order_by('-date'))
        logger.info(data)
        # CSV 导出
        if request.query_params.get('format') == 'csv':
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = 'attachment; filename="daily_stats.csv"'
            writer = csv.writer(response)
            writer.writerow(['日期', '账号数量', 'ins', 'x', 'fb', '发帖数', '回复评论数', '回复消息数', '总曝光量'])
            for r in data:
                writer.writerow([
                    r['date'], r['account_count'], r['ins'], r['x'], r['fb'],
                    r['post_count'], r['reply_comment_count'], r['reply_message_count'], r['total_impressions']
                ])
            return response
        return Response(data)

#
# class CollectTweetsView(APIView):
#     """
#     定时收集推文和评论数据的视图
#     """
#     permission_classes = [IsAuthenticated]
#
#     def get(self, request):
#         """
#         手动触发收集任务
#         """
#         try:
#             self._collect_tweets_data(request.user.id)
#             return Response({'status': 'success', 'message': '数据收集完成'})
#         except Exception as e:
#             logger.error(f"收集推文数据失败: {e}")
#             return Response({'status': 'error', 'message': str(e)})
#
#     def _collect_tweets_data(self, user_id):
#         """
#         收集推文和评论数据的核心逻辑
#         """
#         # 获取用户拥有的所有机器人账号
#         robot_accounts = PoolAccount.objects.filter(
#             owner_id=user_id,
#             is_robot=True,
#             platform='twitter'  # 假设是Twitter平台
#         )
#
#         logger.info(f"找到 {robot_accounts.count()} 个机器人账号")
#
#         for account in robot_accounts:
#             try:
#                 # 初始化Twitter客户端
#                 twitter_client = TwitterUnit(
#                     api_key=account.api_key,
#                     api_secret=account.api_secret,
#                     access_token=account.access_token,
#                     access_token_secret=account.access_token_secret
#                 )
#
#                 # 这里需要根据业务逻辑获取该账号发布的推文ID列表
#                 # 示例：假设有一个方法可以获取最近的推文ID
#                 recent_tweets = self._get_recent_tweets_for_account(account)
#
#                 for tweet_item in recent_tweets:
#                     success, tweet_data = twitter_client.getTwitterData(tweet_item['tweet_id'])
#
#                     if success and tweet_data:
#                         with transaction.atomic():
#                             # 更新或创建推文记录
#                             tweet_obj, created = Tweet.objects.update_or_create(
#                                 tweet_id=tweet_item['tweet_id'],
#                                 platform='twitter',
#                                 defaults={
#                                     'impression_count': tweet_data.get('pageViews', 0),
#                                     'comment_count': tweet_data.get('commentCount', 0),
#                                     'like_count': tweet_data.get('likeCount', 0),
#                                     'created_date': tweet_data.get('createDate', timezone.now().date()),
#                                 }
#                             )
#
#                             # 处理评论数据
#                             comments = tweet_data.get('comments', [])
#                             for comment_data in comments:
#                                 TweetComment.objects.update_or_create(
#                                     comment_id=comment_data['id'],
#                                     tweet=tweet_obj,
#                                     defaults={
#                                         'content': comment_data['text'],
#                                         'commenter_id': comment_data['author_id'],
#                                         'created_at': comment_data['created_at']
#                                     }
#                                 )
#
#             except Exception as e:
#                 logger.error(f"处理账号 {account.username} 时出错: {e}")
#                 continue
#
#     def _get_recent_tweets_for_account(self, account):
#         """
#         获取指定账号的近期推文列表（需要根据实际业务实现）
#         """
#         # 这是一个示例实现，你需要根据实际情况修改
#         # 可能从数据库中查询该账号已知的推文ID，或者通过API获取
#         return [
#             {'tweet_id': '1234567890'},  # 示例推文ID
#         ]
#
#
# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def setup_scheduled_collection(request):
#     """
#     设置定时任务，每6小时执行一次数据收集
#     """
#     # 删除现有的同名计划任务（如果存在）
#     Schedule.objects.filter(name='collect_tweets_data').delete()
#
#     # 创建新的计划任务，每6小时执行一次
#     schedule(
#         'stats.views.CollectTweetsView._collect_tweets_data',
#         request.user.id,
#         name='collect_tweets_data',
#         schedule_type=Schedule.HOURLY,
#         minutes=6 * 60,  # 每6小时
#         repeats=-1  # 无限重复
#     )
#     return Response({
#         'status': 'success',
#         'message': '定时任务已设置，将每6小时执行一次数据收集'
#     })
