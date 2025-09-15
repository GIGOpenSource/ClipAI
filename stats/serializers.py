from rest_framework import serializers


class SummaryResponseSerializer(serializers.Serializer):
    total_runs = serializers.IntegerField()
    succeeded = serializers.IntegerField()
    failed = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_duration_ms = serializers.IntegerField()
    sla_met_rate = serializers.FloatField(allow_null=True)


class ProviderBreakdownItemSerializer(serializers.Serializer):
    provider = serializers.CharField()
    total = serializers.IntegerField()
    succeeded = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_duration_ms = serializers.IntegerField()


class TypeBreakdownItemSerializer(serializers.Serializer):
    task_type = serializers.CharField()
    total = serializers.IntegerField()
    succeeded = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_duration_ms = serializers.IntegerField()


class BreakdownSerializer(serializers.Serializer):
    provider = ProviderBreakdownItemSerializer(many=True)
    type = TypeBreakdownItemSerializer(many=True)


class OverviewResponseSerializer(serializers.Serializer):
    summary = SummaryResponseSerializer()
    breakdown = BreakdownSerializer()
    items = serializers.ListField(child=serializers.DictField(), required=False)


class TaskRunItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    scheduled_task = serializers.IntegerField()
    success = serializers.BooleanField()
    provider = serializers.CharField(allow_null=True)
    task_type = serializers.CharField(allow_null=True)
    duration_ms = serializers.IntegerField(allow_null=True)
    started_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)
    owner_id = serializers.IntegerField(allow_null=True)


class TrendItemSerializer(serializers.Serializer):
    ts = serializers.DateTimeField()
    total = serializers.IntegerField()
    succeeded = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_duration_ms = serializers.IntegerField()


class PaginationSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total = serializers.IntegerField()


class OverviewV2ResponseSerializer(serializers.Serializer):
    summary = serializers.DictField()
    trend = TrendItemSerializer(many=True)
    breakdown = serializers.DictField()
    items = TaskRunItemSerializer(many=True, required=False)
    pagination = PaginationSerializer(required=False)


class DailyTableItemSerializer(serializers.Serializer):
    date = serializers.DateField()
    account_count = serializers.IntegerField()
    ins = serializers.IntegerField()
    x = serializers.IntegerField()
    fb = serializers.IntegerField()
    post_count = serializers.IntegerField()
    reply_comment_count = serializers.IntegerField()
    reply_message_count = serializers.IntegerField()
    total_impressions = serializers.IntegerField()


