from django.contrib import admin
from django import forms
from .models import ScheduledTask, TaskRun, SocialPost, Tag, FollowTarget, FollowAction
from social.models import SocialConfig
from ai.models import AIConfig
from keywords.models import KeywordConfig
from prompts.models import PromptConfig


class ScheduledTaskAdminForm(forms.ModelForm):
    social_config = forms.ModelChoiceField(
        queryset=SocialConfig.objects.all().order_by('provider', 'name'),
        required=False,
        label='社交配置'
    )
    ai_config = forms.ModelChoiceField(
        queryset=AIConfig.objects.all().order_by('-is_default', '-priority', 'name'),
        required=False,
        label='AI 配置'
    )
    keyword_config = forms.ModelChoiceField(
        queryset=KeywordConfig.objects.all().order_by('provider', 'name'),
        required=False,
        label='关键词配置'
    )
    prompt_config = forms.ModelChoiceField(
        queryset=PromptConfig.objects.all().order_by('scene', 'name'),
        required=False,
        label='提示词配置'
    )

    class Meta:
        model = ScheduledTask
        # 用可选下拉替代 *_id 字段，避免手输 ID
        exclude = ('social_config_id', 'ai_config_id', 'keyword_config_id', 'prompt_config_id')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        if inst and inst.pk:
            if inst.social_config_id:
                self.fields['social_config'].initial = SocialConfig.objects.filter(id=inst.social_config_id).first()
            if inst.ai_config_id:
                self.fields['ai_config'].initial = AIConfig.objects.filter(id=inst.ai_config_id).first()
            if inst.keyword_config_id:
                self.fields['keyword_config'].initial = KeywordConfig.objects.filter(id=inst.keyword_config_id).first()
            if inst.prompt_config_id:
                self.fields['prompt_config'].initial = PromptConfig.objects.filter(id=inst.prompt_config_id).first()

    def save(self, commit=True):
        inst: ScheduledTask = super().save(commit=False)
        sc = self.cleaned_data.get('social_config')
        ai = self.cleaned_data.get('ai_config')
        kw = self.cleaned_data.get('keyword_config')
        pr = self.cleaned_data.get('prompt_config')
        inst.social_config_id = sc.pk if sc else None
        inst.ai_config_id = ai.pk if ai else None
        inst.keyword_config_id = kw.pk if kw else None
        inst.prompt_config_id = pr.pk if pr else None
        if commit:
            inst.save()
            self.save_m2m()
        return inst


@admin.register(ScheduledTask)
class ScheduledTaskAdmin(admin.ModelAdmin):
    form = ScheduledTaskAdminForm
    list_display = ('id','owner', 'type', 'provider', 'enabled', 'recurrence_type', 'interval_value', 'time_of_day', 'next_run_at', 'last_run_at', 'status')
    list_filter = ('provider', 'type', 'enabled', 'recurrence_type')
    search_fields = ('owner__username',)
    filter_horizontal = ('tags',)


@admin.register(TaskRun)
class TaskRunAdmin(admin.ModelAdmin):
    list_display = ('id','scheduled_task', 'success', 'provider', 'task_type', 'duration_ms', 'started_at', 'finished_at')
    list_filter = ('provider', 'task_type', 'success', 'sla_met')
    search_fields = ('scheduled_task__id',)

# Register your models here.


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ('id','provider','external_id','owner','posted_at','scheduled_task','task_run')
    list_filter = ('provider',)
    search_fields = ('external_id','owner__username')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('id','name','created_at')
    search_fields = ('name',)


@admin.register(FollowTarget)
class FollowTargetAdmin(admin.ModelAdmin):
    list_display = ('id','owner','provider','username','external_user_id','enabled','source','updated_at')
    list_filter = ('provider','enabled','source')
    search_fields = ('username','external_user_id','owner__username')


@admin.register(FollowAction)
class FollowActionAdmin(admin.ModelAdmin):
    list_display = ('id','owner','provider','social_account','target','status','error_code','executed_at')
    list_filter = ('provider','status')
    search_fields = ('target__username','social_account__external_username','owner__username')


