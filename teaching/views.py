import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from .forms import TeachingRequestForm, TeachingResourceForm
from .models import SchedulingRecommendation, TeachingRequest, TeachingResource
from .services import SchedulingError, confirm_schedule, create_recommendation, interpret_requirement


def is_scheduler(user):
    return bool(user.is_authenticated and
                (user.is_superuser or (hasattr(user, 'profile') and user.profile.role == 'ADMIN')))


def visible_request(request, pk):
    demand = get_object_or_404(TeachingRequest.objects.select_related('requested_by', 'assigned_resource'), pk=pk)
    if demand.requested_by_id != request.user.pk and not is_scheduler(request.user):
        raise PermissionDenied
    return demand


@login_required
def dashboard(request):
    demands = TeachingRequest.objects.select_related('assigned_resource', 'requested_by')
    if not is_scheduler(request.user):
        demands = demands.filter(requested_by=request.user)
    upcoming = demands.filter(
        status=TeachingRequest.Status.CONFIRMED,
        end_at__gte=timezone.now(),
    ).order_by('start_at')[:6]
    return render(request, 'teaching/dashboard.html', {
        'resource_count': TeachingResource.objects.filter(is_active=True).count(),
        'pending_count': demands.filter(status=TeachingRequest.Status.PENDING).count(),
        'confirmed_count': demands.filter(status=TeachingRequest.Status.CONFIRMED).count(),
        'ai_count': SchedulingRecommendation.objects.filter(
            request__in=demands, mode=SchedulingRecommendation.Mode.LLM
        ).count(),
        'upcoming': upcoming,
        'is_scheduler': is_scheduler(request.user),
        'llm_configured': all(os.environ.get(name) for name in (
            'TEACHING_LLM_BASE_URL', 'TEACHING_LLM_API_KEY', 'TEACHING_LLM_MODEL',
        )),
    })


@login_required
def resource_list(request):
    resources = TeachingResource.objects.annotate(
        booking_count=Count('scheduled_requests')
    ).order_by('kind', 'name')
    return render(request, 'teaching/resource_list.html', {
        'resources': resources,
        'is_scheduler': is_scheduler(request.user),
    })


@login_required
def resource_create(request):
    if not is_scheduler(request.user):
        raise PermissionDenied
    form = TeachingResourceForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, '教学资源已建档。')
        return redirect('teaching:resource_list')
    return render(request, 'teaching/form.html', {'form': form, 'heading': '新增教学资源'})


@login_required
def resource_edit(request, pk):
    if not is_scheduler(request.user):
        raise PermissionDenied
    resource = get_object_or_404(TeachingResource, pk=pk)
    form = TeachingResourceForm(request.POST or None, instance=resource)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, '教学资源已更新。')
        return redirect('teaching:resource_list')
    return render(request, 'teaching/form.html', {'form': form, 'heading': f'编辑资源：{resource.name}'})


@login_required
def request_list(request):
    demands = TeachingRequest.objects.select_related('requested_by', 'assigned_resource')
    if not is_scheduler(request.user):
        demands = demands.filter(requested_by=request.user)
    return render(request, 'teaching/request_list.html', {
        'demands': demands,
        'is_scheduler': is_scheduler(request.user),
    })


@login_required
def request_create(request):
    form = TeachingRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        demand = form.save(commit=False)
        demand.requested_by = request.user
        demand.save()
        messages.success(request, '调度需求已提交，可以生成智能建议。')
        return redirect('teaching:request_detail', pk=demand.pk)
    return render(request, 'teaching/form.html', {'form': form, 'heading': '提交教学资源需求'})


@login_required
def request_assistant(request):
    parsed_form = None
    description = ''
    if request.method == 'POST':
        description = request.POST.get('description', '').strip()
        try:
            parsed = interpret_requirement(description)
        except SchedulingError as exc:
            messages.error(request, str(exc))
        else:
            if parsed is None:
                messages.warning(request, 'LLM 未配置、暂不可用或返回了无效结果。请手动填写需求。')
            else:
                parsed_form = TeachingRequestForm(initial=parsed)
                messages.success(request, '已从自然语言中提取需求；请核对并补全开始、结束时间后提交。')
    return render(request, 'teaching/assistant.html', {
        'description': description,
        'parsed_form': parsed_form,
    })


@login_required
def request_detail(request, pk):
    demand = visible_request(request, pk)
    recommendation = demand.recommendations.select_related('suggested_resource').first()
    return render(request, 'teaching/request_detail.html', {
        'demand': demand,
        'recommendation': recommendation,
        'is_scheduler': is_scheduler(request.user),
    })


@login_required
@require_POST
def recommend(request, pk):
    demand = visible_request(request, pk)
    try:
        advice = create_recommendation(demand=demand, user=request.user)
    except SchedulingError as exc:
        messages.error(request, str(exc))
    else:
        if advice.mode == SchedulingRecommendation.Mode.LLM:
            messages.success(request, 'LLM 辅助建议已生成；最终排程需管理员确认。')
        else:
            messages.info(request, '规则建议已生成；未配置 LLM 或模型不可用。')
    return redirect('teaching:request_detail', pk=pk)


@login_required
@require_POST
def confirm(request, pk):
    if not is_scheduler(request.user):
        raise PermissionDenied
    demand = visible_request(request, pk)
    try:
        resource_id = int(request.POST.get('resource_id', ''))
        confirm_schedule(demand_id=demand.pk, resource_id=resource_id, user=request.user)
    except (SchedulingError, ValueError) as exc:
        messages.error(request, str(exc) if isinstance(exc, SchedulingError) else '请选择有效资源。')
    else:
        messages.success(request, '排程已确认，资源时段已占用。')
    return redirect('teaching:request_detail', pk=pk)


@login_required
@require_POST
def cancel(request, pk):
    demand = visible_request(request, pk)
    if demand.status == TeachingRequest.Status.CONFIRMED and not is_scheduler(request.user):
        raise PermissionDenied
    if demand.status != TeachingRequest.Status.CANCELLED:
        demand.status = TeachingRequest.Status.CANCELLED
        demand.save(update_fields=['status', 'updated_at'])
        messages.success(request, '需求已取消。')
    return redirect('teaching:request_detail', pk=pk)
