from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class TeachingResource(models.Model):
    class Kind(models.TextChoices):
        CLASSROOM = 'CLASSROOM', '普通教室'
        LAB = 'LAB', '实验室'
        EQUIPMENT = 'EQUIPMENT', '教学设备'
        ONLINE = 'ONLINE', '在线教学平台'

    name = models.CharField('资源名称', max_length=100)
    code = models.CharField('资源编码', max_length=30, unique=True)
    kind = models.CharField('资源类型', max_length=12, choices=Kind.choices)
    location = models.CharField('位置或访问方式', max_length=120, blank=True)
    capacity = models.PositiveIntegerField('可容纳人数', validators=[MinValueValidator(1)])
    features = models.CharField('能力标签', max_length=300, blank=True, help_text='用逗号分隔，例如：投影,录播,无障碍')
    description = models.TextField('说明', blank=True)
    is_active = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['kind', 'name']
        verbose_name = '教学资源'
        verbose_name_plural = '教学资源'

    def __str__(self):
        return f'{self.name}（{self.code}）'

    def clean(self):
        if not self.pk:
            return
        previous = type(self).objects.filter(pk=self.pk).first()
        if previous and any(getattr(previous, field) != getattr(self, field)
                            for field in ('kind', 'capacity', 'features')):
            if self.scheduled_requests.filter(
                status=TeachingRequest.Status.CONFIRMED,
                end_at__gte=timezone.now(),
            ).exists():
                raise ValidationError('此资源存在未来排程，不能修改类型、容量或能力标签；可修改名称、位置和说明。')


class TeachingRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', '待调度'
        CONFIRMED = 'CONFIRMED', '已确认'
        CANCELLED = 'CANCELLED', '已取消'

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='teaching_requests')
    title = models.CharField('教学活动', max_length=120)
    course = models.CharField('课程名称', max_length=120)
    start_at = models.DateTimeField('开始时间')
    end_at = models.DateTimeField('结束时间')
    expected_attendees = models.PositiveIntegerField('预计人数', validators=[MinValueValidator(1)])
    resource_kind = models.CharField('所需资源类型', max_length=12, choices=TeachingResource.Kind.choices)
    required_features = models.CharField('必需能力标签', max_length=300, blank=True)
    notes = models.TextField('需求说明', blank=True)
    status = models.CharField('状态', max_length=10, choices=Status.choices, default=Status.PENDING)
    assigned_resource = models.ForeignKey(TeachingResource, on_delete=models.PROTECT, null=True, blank=True, related_name='scheduled_requests')
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_teaching_requests')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['status', 'start_at', 'end_at'])]
        verbose_name = '教学调度需求'
        verbose_name_plural = '教学调度需求'

    def clean(self):
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError({'end_at': '结束时间必须晚于开始时间。'})
        if self.status == self.Status.CONFIRMED and not self.assigned_resource_id:
            raise ValidationError({'assigned_resource': '已确认的需求必须分配资源。'})

    def __str__(self):
        return f'{self.course} · {self.title}'


class SchedulingRecommendation(models.Model):
    class Mode(models.TextChoices):
        LLM = 'LLM', 'LLM 辅助'
        RULES = 'RULES', '规则推荐'

    request = models.ForeignKey(TeachingRequest, on_delete=models.CASCADE, related_name='recommendations')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    mode = models.CharField('推荐模式', max_length=5, choices=Mode.choices)
    suggested_resource = models.ForeignKey(TeachingResource, on_delete=models.SET_NULL, null=True, blank=True)
    candidates = models.JSONField('候选评分', default=list)
    explanation = models.TextField('推荐解释')
    alternatives = models.JSONField('替代时段', default=list)
    llm_model = models.CharField('模型名称', max_length=100, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = '智能调度建议'
        verbose_name_plural = '智能调度建议'
