# sherlock-python/inventory/admin.py

from django.contrib import admin
from .models import (
    Section,
    Space,
    Item,
    PrintQueue,
    PrintQueueItem,
    ClubMember,
    Requisition,
    RequisitionItem,
    ReturnRecord,
    ReturnItem,
    StockTransaction,
    InventoryCount,
    InventoryCountItem,
)

admin.site.register(Section)
admin.site.register(Space)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'space', 'quantity', 'unit', 'material_type', 'warning_quantity', 'is_active')
    list_filter = ('material_type', 'is_active', 'space__section')
    search_fields = ('name', 'barcode')
    readonly_fields = ('quantity', 'barcode', 'original_section_code', 'original_space_code')
admin.site.register(PrintQueue)
admin.site.register(PrintQueueItem)
admin.site.register(ClubMember)
admin.site.register(Requisition)
admin.site.register(RequisitionItem)
admin.site.register(ReturnRecord)
admin.site.register(ReturnItem)


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('occurred_at', 'item', 'transaction_type', 'quantity_change', 'balance_after', 'user', 'reference_type')
    list_filter = ('transaction_type', 'reference_type')
    search_fields = ('item__name', 'source_key', 'reason')
    readonly_fields = [field.name for field in StockTransaction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
admin.site.register(InventoryCount)
admin.site.register(InventoryCountItem)
