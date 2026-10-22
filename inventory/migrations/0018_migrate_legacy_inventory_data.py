from django.db import migrations


def copy_legacy_data(apps, schema_editor):
    Student = apps.get_model('inventory', 'Student')
    ClubMember = apps.get_model('inventory', 'ClubMember')
    ItemLog = apps.get_model('inventory', 'ItemLog')
    StockTransaction = apps.get_model('inventory', 'StockTransaction')

    for student in Student.objects.all().iterator():
        department = ' '.join(
            value for value in [student.student_class, student.section] if value
        )[:100]
        ClubMember.objects.get_or_create(
            member_code=student.admission_number,
            defaults={
                'name': student.name,
                'department': department,
            },
        )

    action_map = {
        'RECEIVED': 'INBOUND',
        'DAMAGED': 'DAMAGED',
        'LOST': 'LOST',
        'CORR_ADD': 'ADJUST_ADD',
        'CORR_SUB': 'ADJUST_SUB',
    }
    for old_log in ItemLog.objects.order_by('timestamp', 'pk').iterator():
        transaction_type = action_map.get(old_log.action)
        if not transaction_type or old_log.quantity_change == 0:
            continue

        transaction, created = StockTransaction.objects.get_or_create(
            source_key=f'legacy:item-log:{old_log.pk}',
            defaults={
                'item_id': old_log.item_id,
                'transaction_type': transaction_type,
                'quantity_change': old_log.quantity_change,
                'user_id': old_log.user_id,
                'reference_type': 'LEGACY_ITEM_LOG',
                'reference_id': old_log.pk,
                'reason': old_log.notes,
            },
        )
        if created:
            StockTransaction.objects.filter(pk=transaction.pk).update(
                occurred_at=old_log.timestamp
            )


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0017_refactor_requisition_stock_models'),
    ]

    operations = [
        migrations.RunPython(copy_legacy_data, migrations.RunPython.noop),
    ]
