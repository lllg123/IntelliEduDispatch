"""Transactional application services for the club inventory workflows."""

import uuid

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    ClubMember,
    Item,
    ItemLog,
    Requisition,
    RequisitionItem,
    ReturnItem,
    ReturnRecord,
    StockTransaction,
    InventoryCount,
    InventoryCountItem,
)


class WorkflowError(Exception):
    """A user-correctable business workflow error."""


class InsufficientStockError(WorkflowError):
    """Raised when an issue would make the on-hand balance negative."""


def _is_admin(user):
    return bool(
        user
        and user.is_authenticated
        and hasattr(user, 'profile')
        and user.profile.role == 'ADMIN'
    )


def _member_can_manage(user, member):
    return _is_admin(user) or member.user_id == user.id


def get_or_create_member_for_user(user):
    """Return the member profile for a login, creating a minimal one if needed."""
    member, _ = ClubMember.objects.get_or_create(
        user=user,
        defaults={
            'member_code': f'USER-{user.pk}',
            'name': user.get_full_name() or user.username,
        },
    )
    return member


@transaction.atomic
def create_requisition(*, member, user, purpose, notes='', planned_return_date=None):
    if not member.is_active:
        raise WorkflowError('该成员已停用，不能创建领用申请。')
    if not purpose or not purpose.strip():
        raise WorkflowError('请填写领用用途。')
    if not _member_can_manage(user, member):
        raise WorkflowError('不能为其他成员创建领用申请。')
    return Requisition.objects.create(
        member=member,
        created_by=user,
        purpose=purpose.strip(),
        notes=notes.strip(),
        planned_return_date=planned_return_date,
    )


@transaction.atomic
def add_requisition_item(*, requisition_id, item_id, quantity, user, notes=''):
    requisition = Requisition.objects.select_for_update().select_related('member').get(id=requisition_id)
    if not _member_can_manage(user, requisition.member):
        raise WorkflowError('不能修改其他成员的领用申请。')
    if requisition.status != Requisition.Status.DRAFT:
        raise WorkflowError('只有草稿状态的申请可以修改。')
    if quantity <= 0:
        raise WorkflowError('申请数量必须大于 0。')

    item = Item.objects.get(id=item_id)
    if not item.is_active:
        raise WorkflowError(f'物资“{item.name}”已停用，不能加入申请。')

    line, created = RequisitionItem.objects.get_or_create(
        requisition=requisition,
        item=item,
        defaults={'quantity_requested': quantity, 'notes': notes.strip()},
    )
    if not created:
        line.quantity_requested += quantity
        if notes.strip():
            line.notes = notes.strip()
        line.save(update_fields=['quantity_requested', 'notes'])
    return line


@transaction.atomic
def remove_requisition_item(*, requisition_id, line_id, user):
    requisition = Requisition.objects.select_for_update().select_related('member').get(id=requisition_id)
    if not _member_can_manage(user, requisition.member):
        raise WorkflowError('不能修改其他成员的领用申请。')
    if requisition.status != Requisition.Status.DRAFT:
        raise WorkflowError('只有草稿状态的申请可以修改。')
    line = RequisitionItem.objects.get(id=line_id, requisition=requisition)
    line.delete()


@transaction.atomic
def submit_requisition(*, requisition_id, user):
    requisition = Requisition.objects.select_for_update().select_related('member').get(id=requisition_id)
    if not _member_can_manage(user, requisition.member):
        raise WorkflowError('不能提交其他成员的领用申请。')
    if requisition.status in {
        Requisition.Status.SUBMITTED,
        Requisition.Status.APPROVED,
        Requisition.Status.ISSUED,
        Requisition.Status.COMPLETED,
    }:
        return requisition
    if requisition.status != Requisition.Status.DRAFT:
        raise WorkflowError('当前申请状态不能提交。')
    if not requisition.lines.exists():
        raise WorkflowError('申请至少需要一项物资。')
    if not requisition.member.is_active:
        raise WorkflowError('申请成员已停用，不能提交申请。')
    if requisition.lines.filter(item__is_active=False).exists():
        raise WorkflowError('申请中包含已停用物资，请先修改申请。')

    requisition.status = Requisition.Status.SUBMITTED
    requisition.submitted_at = timezone.now()
    requisition.save(update_fields=['status', 'submitted_at', 'updated_at'])
    return requisition


@transaction.atomic
def approve_requisition(*, requisition_id, user):
    requisition = Requisition.objects.select_for_update().get(id=requisition_id)
    if not _is_admin(user):
        raise WorkflowError('只有管理员可以审批领用申请。')
    if requisition.status in {
        Requisition.Status.APPROVED,
        Requisition.Status.ISSUED,
        Requisition.Status.COMPLETED,
    }:
        return requisition
    if requisition.status != Requisition.Status.SUBMITTED:
        raise WorkflowError('只有待审批申请可以批准。')

    lines = list(requisition.lines.select_for_update().select_related('item'))
    if not lines:
        raise WorkflowError('申请没有明细，不能批准。')
    for line in lines:
        if not line.item.is_active:
            raise WorkflowError(f'物资“{line.item.name}”已停用，不能批准。')
        line.quantity_approved = line.quantity_requested
        line.save(update_fields=['quantity_approved'])

    requisition.status = Requisition.Status.APPROVED
    requisition.approved_at = timezone.now()
    requisition.reject_reason = ''
    requisition.save(update_fields=['status', 'approved_at', 'reject_reason', 'updated_at'])
    return requisition


@transaction.atomic
def reject_requisition(*, requisition_id, user, reason):
    requisition = Requisition.objects.select_for_update().get(id=requisition_id)
    if not _is_admin(user):
        raise WorkflowError('只有管理员可以驳回领用申请。')
    if requisition.status == Requisition.Status.REJECTED:
        return requisition
    if requisition.status != Requisition.Status.SUBMITTED:
        raise WorkflowError('只有待审批申请可以驳回。')
    if not reason or not reason.strip():
        raise WorkflowError('驳回申请必须填写原因。')

    requisition.status = Requisition.Status.REJECTED
    requisition.reject_reason = reason.strip()
    requisition.save(update_fields=['status', 'reject_reason', 'updated_at'])
    return requisition


@transaction.atomic
def cancel_requisition(*, requisition_id, user):
    requisition = Requisition.objects.select_for_update().select_related('member').get(id=requisition_id)
    if not _member_can_manage(user, requisition.member):
        raise WorkflowError('不能撤回其他成员的领用申请。')
    if requisition.status == Requisition.Status.CANCELLED:
        return requisition
    if requisition.status not in {Requisition.Status.DRAFT, Requisition.Status.SUBMITTED}:
        raise WorkflowError('当前申请状态不能撤回。')

    requisition.status = Requisition.Status.CANCELLED
    requisition.cancelled_at = timezone.now()
    requisition.save(update_fields=['status', 'cancelled_at', 'updated_at'])
    return requisition


@transaction.atomic
def issue_requisition(*, requisition_id, user):
    """Approve-issued stock atomically; repeated calls after success are harmless."""
    if not _is_admin(user):
        raise WorkflowError('只有管理员可以执行出库。')

    requisition = Requisition.objects.select_for_update().get(id=requisition_id)
    if requisition.status in {Requisition.Status.ISSUED, Requisition.Status.COMPLETED}:
        return requisition
    if requisition.status != Requisition.Status.APPROVED:
        raise WorkflowError('只有已批准申请可以执行出库。')

    lines = list(requisition.lines.select_for_update().order_by('item_id'))
    if not lines:
        raise WorkflowError('申请没有明细，不能出库。')

    for line in lines:
        quantity = line.quantity_approved
        if quantity <= 0:
            raise WorkflowError(f'物资“{line.item.name}”没有有效批准数量。')
        item = Item.objects.select_for_update().get(id=line.item_id)
        if not item.is_active:
            raise WorkflowError(f'物资“{item.name}”已停用，不能出库。')
        if item.quantity < quantity:
            raise InsufficientStockError(
                f'物资“{item.name}”库存不足：需要 {quantity}{item.unit}，当前只有 {item.quantity}{item.unit}。'
            )

        item.quantity -= quantity
        item.save(update_fields=['quantity', 'updated_at'])
        StockTransaction.objects.create(
            item=item,
            transaction_type=StockTransaction.TransactionType.ISSUE,
            quantity_change=-quantity,
            balance_after=item.quantity,
            user=user,
            reference_type='REQUISITION_ITEM',
            reference_id=line.id,
            source_key=f'requisition:{requisition.id}:line:{line.id}:issue',
            reason=f'领用申请 {requisition.request_no}',
        )
        line.quantity_issued = quantity
        line.save(update_fields=['quantity_issued'])

    # Consumables are complete once issued. Reusable materials remain in the
    # issued state until every outstanding quantity has been returned.
    has_reusable_outstanding = any(
        line.item.material_type == Item.MaterialType.REUSABLE
        and line.quantity_issued > line.quantity_returned
        for line in lines
    )
    requisition.status = (
        Requisition.Status.ISSUED
        if has_reusable_outstanding
        else Requisition.Status.COMPLETED
    )
    requisition.issued_at = timezone.now()
    requisition.save(update_fields=['status', 'issued_at', 'updated_at'])
    return requisition


@transaction.atomic
def submit_return(*, return_record_id, user):
    return_record = ReturnRecord.objects.select_for_update().select_related('member').get(id=return_record_id)
    if not _member_can_manage(user, return_record.member):
        raise WorkflowError('不能提交其他成员的归还单。')
    if return_record.status == ReturnRecord.Status.SUBMITTED:
        return return_record
    if return_record.status != ReturnRecord.Status.DRAFT:
        raise WorkflowError('当前归还单状态不能提交。')
    if not return_record.lines.exists():
        raise WorkflowError('归还单至少需要一项物资。')

    return_record.status = ReturnRecord.Status.SUBMITTED
    return_record.submitted_at = timezone.now()
    return_record.save(update_fields=['status', 'submitted_at', 'updated_at'])
    return return_record


@transaction.atomic
def confirm_return(*, return_record_id, user):
    """Confirm returns and write return/damage/loss ledger entries atomically."""
    if not _is_admin(user):
        raise WorkflowError('只有管理员可以确认归还。')

    return_record = ReturnRecord.objects.select_for_update().get(id=return_record_id)
    if return_record.status == ReturnRecord.Status.CONFIRMED:
        return return_record
    if return_record.status != ReturnRecord.Status.SUBMITTED:
        raise WorkflowError('只有待验收归还单可以确认。')

    lines = list(return_record.lines.select_related('requisition_item__requisition').order_by('requisition_item__item_id'))
    if not lines:
        raise WorkflowError('归还单没有明细，不能确认。')

    affected_requisitions = set()
    for return_line in lines:
        issued_line = RequisitionItem.objects.select_for_update().select_related('requisition').get(
            id=return_line.requisition_item_id
        )
        if issued_line.requisition.member_id != return_record.member_id:
            raise WorkflowError('归还明细与归还成员不匹配。')
        if issued_line.requisition.status not in {
            Requisition.Status.ISSUED,
            Requisition.Status.COMPLETED,
        }:
            raise WorkflowError('只有已出库申请的明细可以归还。')
        if issued_line.item.material_type != Item.MaterialType.REUSABLE:
            raise WorkflowError(f'耗材“{issued_line.item.name}”不支持归还。')
        if return_line.quantity > issued_line.quantity_still_out:
            raise WorkflowError(
                f'“{issued_line.item.name}”归还数量超过尚未归还数量。'
            )

        item = Item.objects.select_for_update().get(id=issued_line.item_id)
        original_balance = item.quantity
        restored_balance = original_balance + return_line.quantity

        item.quantity = restored_balance
        item.save(update_fields=['quantity', 'updated_at'])
        StockTransaction.objects.create(
            item=item,
            transaction_type=StockTransaction.TransactionType.RETURN,
            quantity_change=return_line.quantity,
            balance_after=restored_balance,
            user=user,
            reference_type='RETURN_ITEM',
            reference_id=return_line.id,
            source_key=f'return:{return_record.id}:line:{return_line.id}:return',
            reason=f'归还单 {return_record.return_no}',
        )

        if return_line.condition in {ReturnItem.Condition.DAMAGED, ReturnItem.Condition.LOST}:
            item.quantity = original_balance
            item.save(update_fields=['quantity', 'updated_at'])
            loss_type = (
                StockTransaction.TransactionType.DAMAGED
                if return_line.condition == ReturnItem.Condition.DAMAGED
                else StockTransaction.TransactionType.LOST
            )
            StockTransaction.objects.create(
                item=item,
                transaction_type=loss_type,
                quantity_change=-return_line.quantity,
                balance_after=original_balance,
                user=user,
                reference_type='RETURN_ITEM',
                reference_id=return_line.id,
                source_key=f'return:{return_record.id}:line:{return_line.id}:loss',
                reason=return_line.notes or f'归还验收：{return_line.get_condition_display()}',
            )

        issued_line.quantity_returned += return_line.quantity
        issued_line.save(update_fields=['quantity_returned'])
        affected_requisitions.add(issued_line.requisition_id)

    return_record.status = ReturnRecord.Status.CONFIRMED
    return_record.processed_by = user
    return_record.confirmed_at = timezone.now()
    return_record.save(update_fields=['status', 'processed_by', 'confirmed_at', 'updated_at'])

    for requisition_id in affected_requisitions:
        requisition = Requisition.objects.select_for_update().get(id=requisition_id)
        if requisition.status == Requisition.Status.ISSUED and not requisition.lines.filter(
            quantity_issued__gt=F('quantity_returned')
        ).exists():
            requisition.status = Requisition.Status.COMPLETED
            requisition.save(update_fields=['status', 'updated_at'])

    return return_record


@transaction.atomic
def record_stock_adjustment(*, item_id, user, action, quantity, notes):
    """Update stock and write both the new ledger and a legacy compatibility log."""
    if not _is_admin(user):
        raise WorkflowError('只有管理员可以调整库存。')
    if quantity <= 0:
        raise WorkflowError('库存调整数量必须大于 0。')
    item = Item.objects.select_for_update().get(id=item_id)

    add_actions = {'RECEIVED', 'CORR_ADD'}
    subtract_actions = {'DAMAGED', 'LOST', 'CORR_SUB'}
    transaction_types = {
        'RECEIVED': StockTransaction.TransactionType.INBOUND,
        'CORR_ADD': StockTransaction.TransactionType.ADJUST_ADD,
        'DAMAGED': StockTransaction.TransactionType.DAMAGED,
        'LOST': StockTransaction.TransactionType.LOST,
        'CORR_SUB': StockTransaction.TransactionType.ADJUST_SUB,
    }
    if action not in transaction_types:
        raise WorkflowError('无效的库存调整类型。')
    if action in subtract_actions and quantity > item.quantity:
        raise InsufficientStockError(
            f'不能减少 {quantity}{item.unit}，当前库存只有 {item.quantity}{item.unit}。'
        )

    quantity_change = quantity if action in add_actions else -quantity
    item.quantity += quantity_change
    item.save(update_fields=['quantity', 'updated_at'])

    StockTransaction.objects.create(
        item=item,
        transaction_type=transaction_types[action],
        quantity_change=quantity_change,
        balance_after=item.quantity,
        user=user,
        reference_type='MANUAL_ADJUSTMENT',
        reference_id=item.id,
        source_key=f'manual:{uuid.uuid4()}',
        reason=notes.strip(),
    )
    ItemLog.objects.create(
        item=item,
        user=user,
        action=action,
        quantity_change=quantity_change,
        notes=notes.strip(),
    )
    return item


@transaction.atomic
def create_inventory_count(*, user, notes=''):
    """Create an administrator-owned count with a quantity snapshot."""
    if not _is_admin(user):
        raise WorkflowError('只有管理员可以创建盘点单。')

    count = InventoryCount.objects.create(created_by=user, notes=notes.strip())
    items = Item.objects.select_for_update().filter(is_active=True).order_by('id')
    InventoryCountItem.objects.bulk_create([
        InventoryCountItem(
            inventory_count=count,
            item=item,
            system_quantity=item.quantity,
            counted_quantity=item.quantity,
        )
        for item in items
    ])
    return count


@transaction.atomic
def confirm_inventory_count(*, count_id, user):
    """Reconcile a count snapshot and write one ledger entry per difference."""
    if not _is_admin(user):
        raise WorkflowError('只有管理员可以确认盘点单。')

    count = InventoryCount.objects.select_for_update().get(id=count_id)
    if count.status == InventoryCount.Status.CONFIRMED:
        return count
    if count.status != InventoryCount.Status.DRAFT:
        raise WorkflowError('只有草稿状态的盘点单可以确认。')

    lines = list(count.lines.select_for_update().order_by('item_id'))
    if not lines:
        raise WorkflowError('盘点单没有物资明细，不能确认。')

    for line in lines:
        if line.counted_quantity < 0:
            raise WorkflowError(f'“{line.item.name}”的实盘数量不能为负数。')
        item = Item.objects.select_for_update().get(id=line.item_id)
        if item.quantity != line.system_quantity:
            raise WorkflowError(
                f'“{item.name}”在盘点期间库存已变化，请重新创建盘点单。'
            )

        difference = line.counted_quantity - line.system_quantity
        if difference == 0:
            continue

        item.quantity = line.counted_quantity
        item.save(update_fields=['quantity', 'updated_at'])
        transaction_type = (
            StockTransaction.TransactionType.ADJUST_ADD
            if difference > 0
            else StockTransaction.TransactionType.ADJUST_SUB
        )
        StockTransaction.objects.create(
            item=item,
            transaction_type=transaction_type,
            quantity_change=difference,
            balance_after=item.quantity,
            user=user,
            reference_type='INVENTORY_COUNT_ITEM',
            reference_id=line.id,
            source_key=f'count:{count.id}:item:{line.id}',
            reason=line.reason.strip() or count.notes.strip() or '盘点差异调整',
        )

    count.status = InventoryCount.Status.CONFIRMED
    count.confirmed_by = user
    count.confirmed_at = timezone.now()
    count.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'updated_at'])
    return count
