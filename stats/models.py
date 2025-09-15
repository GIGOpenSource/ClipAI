from django.db import models


class StatsBoard(models.Model):
    class Meta:
        managed = False
        verbose_name = '数据统计'
        verbose_name_plural = '数据统计'


class DailyStat(models.Model):
    date = models.DateField(db_index=True)
    owner_id = models.IntegerField(null=True, blank=True, db_index=True)
    account_count = models.IntegerField(default=0)
    ins = models.IntegerField(default=0)
    x = models.IntegerField(default=0)
    fb = models.IntegerField(default=0)
    post_count = models.IntegerField(default=0)
    reply_comment_count = models.IntegerField(default=0)
    reply_message_count = models.IntegerField(default=0)
    total_impressions = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('date', 'owner_id')
        ordering = ['-date']
        verbose_name = '日统计'
        verbose_name_plural = '日统计'


# Create your models here.
