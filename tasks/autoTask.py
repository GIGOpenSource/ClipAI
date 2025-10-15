from background_task import background
from background_task.models import Task
from django.utils import timezone
from datetime import datetime, timedelta


# 你的目标方法
def get_data():
    """需要定时执行的方法"""
    from utils.utils import logger
    try:
        logger.info("开始获取数据...")
        print("获取数据...")
        # 实际业务逻辑...
        result = "数据获取完成"
        logger.info(result)
        return result
    except Exception as e:
        logger.error(f"获取数据时出错: {str(e)}")
        raise


@background(schedule=0)
def scheduled_get_data(repeat_times=1):
    """
    定时执行的任务包装器
    :param repeat_times: 本次计划需要执行的总次数
    """
    # 执行目标方法
    # 检查是否需要继续执行（还剩多少次）
    remaining = repeat_times - 1
    print("任务包装器")
    if remaining > 0:
        # 10分钟后再次执行（可根据需要调整间隔）
        scheduled_get_data(remaining, schedule=timedelta(minutes=10))


def schedule_daily_task(hour, minute, repeat_times=1):
    """
    安排每天指定时间执行N次任务
    :param hour: 小时（0-23）
    :param minute: 分钟（0-59）
    :param repeat_times: 执行次数
    """
    # 计算今天的目标时间
    now = timezone.now()
    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    print("每日任务调度")
    # 如果目标时间已过，安排到明天
    if target_time < now:
        target_time += timedelta(days=1)

    # 计算距离目标时间的秒数
    schedule_seconds = (target_time - now).total_seconds()

    # 创建任务（每天重复）
    Task.objects.create(
        task_name='tasks.autoTask.scheduled_get_data',
        # 使用正确的参数格式
        task_params=f'[[{repeat_times}], {{}}]', # 传递 repeat_times 参数
        run_at=target_time,  # 使用正确的字段名
        repeat=Task.DAILY,  # 每天重复
        queue='default'  # 添加队列名称
    )

def schedule_date_task(target_date, repeat_times=1):
    """
    安排指定日期执行N次任务
    :param target_date: 日期（datetime对象）
    :param repeat_times: 执行次数
    """
    now = timezone.now()
    print("指定日期任务调度")
    if target_date < now:
        raise ValueError("目标日期不能早于当前时间")

    # 创建一次性任务 - 修复参数名
    from background_task.models import Task
    Task.objects.create(
        task_name='tasks.autoTask.scheduled_get_data',
        task_params=f'[{{"value": {repeat_times}, "name": "repeat_times", "type": "int"}}]',  # 修正参数传递方式
        run_at=target_date  # 修正参数名
    )