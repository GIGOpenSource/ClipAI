#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：ClipAI 
@File    ：scheduleUnit.py
@Author  ：LYP
@Date    ：2025/10/15 9:37 
@description :定时任务调度
"""
import traceback
from django.conf import settings
from apscheduler.schedulers.background import BackgroundScheduler
# 特定时间执行一次任务
from apscheduler.triggers.date import DateTrigger
# 间隔性时间任务
from apscheduler.triggers.interval import IntervalTrigger
# 重复性时间任务
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.models import DjangoJobExecution
from django_apscheduler import util
from django_apscheduler.jobstores import DjangoJobStore

from utils.utils import logger


@util.close_old_connections
def delete_old_job_executions(max_age=60):
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


def createScheduleTriggers(triggersType: str = 'date' or 'interval' or 'cron', *args, **kwargs):
    """
    获取定时任务触发器
    :param triggersType: date,interval,cron
    :param args:
    :param kwargs:
    :return:
    """
    if triggersType == "date":
        triggers = DateTrigger(**kwargs)
    elif triggersType == "interval":
        triggers = IntervalTrigger(**kwargs)
    else:
        triggers = CronTrigger(**kwargs)
    return triggers
