from django.contrib import admin

from .models import SchedulingRecommendation, TeachingRequest, TeachingResource

admin.site.site_header = '智慧教学资源智能调度系统管理'
admin.site.site_title = '智慧教学资源智能调度系统'
admin.site.index_title = '资源与排程管理'


@admin.register(TeachingResource)
class TeachingResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'kind', 'capacity', 'location', 'is_active')
    list_filter = ('kind', 'is_active')
    search_fields = ('name', 'code', 'features')


@admin.register(TeachingRequest)
class TeachingRequestAdmin(admin.ModelAdmin):
    list_display = ('course', 'title', 'start_at', 'status', 'assigned_resource', 'requested_by')
    list_filter = ('status', 'resource_kind')
    search_fields = ('course', 'title')
    readonly_fields = ('status', 'assigned_resource', 'confirmed_by', 'confirmed_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SchedulingRecommendation)
class SchedulingRecommendationAdmin(admin.ModelAdmin):
    list_display = ('request', 'mode', 'suggested_resource', 'llm_model', 'created_at')
    readonly_fields = [field.name for field in SchedulingRecommendation._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
