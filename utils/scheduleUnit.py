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


def createSchedule(triggersType: str, *args, **kwargs):
    """
    创建任务
    :param triggersType: one,interval
    :param args:
    :param kwargs:
    :return:
    """
    schedule_task = BackgroundScheduler(timezone=settings.TIME_ZONE)
    schedule_task.add_jobstore(DjangoJobStore(), "default")
    if triggersType == "one":
        triggers = DateTrigger(run_date=kwargs.get("run_date"))
    if triggersType == "interval":
        triggers = IntervalTrigger(**kwargs)
