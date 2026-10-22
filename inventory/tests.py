# sherlock-python/inventory/tests.py

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import (
    Section,
    Space,
    Item,
    Student,
    CheckoutLog,
    CheckInLog,
    ItemLog,
    ClubMember,
    Requisition,
    RequisitionItem,
    ReturnRecord,
    ReturnItem,
    StockTransaction,
    InventoryCount,
    InventoryCountItem,
)
from .services import (
    InsufficientStockError,
    WorkflowError,
    add_requisition_item,
    approve_requisition,
    confirm_return,
    create_requisition,
    create_inventory_count,
    confirm_inventory_count,
    issue_requisition,
    record_stock_adjustment,
    reject_requisition,
    submit_requisition,
    submit_return,
)
from .forms import ItemForm

# ==============================================================================
#  MODEL TESTS
# ==============================================================================

class ModelTests(TestCase):
    """Tests for custom logic within the application's models."""

    @classmethod
    def setUpTestData(cls):
        """Set up non-modified objects used by all test methods."""
        cls.user = User.objects.create_user(username='testuser', password='password')
        cls.student = Student.objects.create(name='Test Student', admission_number='T001', student_class='X', section='A')
        cls.section = Section.objects.create(name='Test Section', section_code=1)
        cls.space = Space.objects.create(name='Test Space', section=cls.section, space_code=1, original_section_code=1)
        cls.item = Item.objects.create(
            name='Test Item',
            space=cls.space,
            item_code=1,
            quantity=20,
            buffer_quantity=5
        )

    def test_item_quantity_properties(self):
        """Test the quantity calculation properties of the Item model."""
        self.assertEqual(self.item.checked_out_quantity, 0)
        self.assertEqual(self.item.available_quantity, 15) 

        CheckoutLog.objects.create(item=self.item, student=self.student, quantity=8, due_date=timezone.now())
        self.assertEqual(self.item.checked_out_quantity, 8)
        self.assertEqual(self.item.available_quantity, 7)  

    def test_checkout_log_is_overdue(self):
        """Test the is_overdue property of the CheckoutLog model."""
        future_log = CheckoutLog.objects.create(item=self.item, student=self.student, quantity=1, due_date=timezone.now() + timedelta(days=1))
        self.assertFalse(future_log.is_overdue)

        past_log = CheckoutLog.objects.create(item=self.item, student=self.student, quantity=1, due_date=timezone.now() - timedelta(days=1))
        self.assertTrue(past_log.is_overdue)

        past_log.return_date = timezone.now()
        past_log.save()
        self.assertFalse(past_log.is_overdue)

    def test_checkout_log_partial_returns(self):
        """Test the quantity calculation properties of the CheckoutLog model."""
        log = CheckoutLog.objects.create(item=self.item, student=self.student, quantity=10, due_date=timezone.now())
        self.assertEqual(log.quantity_returned_so_far, 0)
        self.assertEqual(log.quantity_still_on_loan, 10)

        CheckInLog.objects.create(checkout_log=log, quantity_returned=4)
        log.refresh_from_db() 
        self.assertEqual(log.quantity_returned_so_far, 4)
        self.assertEqual(log.quantity_still_on_loan, 6)

# ==============================================================================
#  VIEW & WORKFLOW TESTS
# ==============================================================================

class ViewAndWorkflowTests(TestCase):
    """
    A suite of tests to verify that pages load, are protected, and that
    key user workflows function correctly from end-to-end.
    """
    def setUp(self):
        """Set up a logged-in client and base data for all view tests."""
        self.user = User.objects.create_superuser(
            username='testuser',
            email='test@example.com',
            password='password123',
        )
        self.client.login(username='testuser', password='password123')
        
        self.section = Section.objects.create(name='Test Section', section_code=1)
        self.space = Space.objects.create(name='Test Space', section=self.section, space_code=1, original_section_code=1)
        self.item = Item.objects.create(name='Test Item', space=self.space, item_code=1, quantity=10)
        self.student = Student.objects.create(name='Test Student', admission_number='T001', student_class='X', section='A')

    def test_all_pages_load_correctly(self):
        """Test that all main pages return a 200 OK status code for a logged-in user."""
        urls = [
            reverse('inventory:dashboard'),
            reverse('inventory:inventory_browser'),
            reverse('inventory:section_detail', args=[self.section.section_code]),
            reverse('inventory:space_detail', args=[self.section.section_code, self.space.space_code]),
            reverse('inventory:item_detail', args=[self.section.section_code, self.space.space_code, self.item.item_code]),
            reverse('inventory:student_list'),
            reverse('inventory:student_detail', args=[self.student.id]),
            reverse('inventory:on_loan_dashboard'),
            reverse('inventory:overdue_report'),
            reverse('inventory:low_stock_report'),
            reverse('inventory:search'),
            reverse('inventory:print_queue'),
            reverse('inventory:requisition_list'),
            reverse('inventory:inventory_count_list'),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"Failed to load page: {url}")

    def test_pages_redirect_if_not_logged_in(self):
        """Test that a protected page redirects to the login screen for an anonymous user."""
        self.client.logout()
        response = self.client.get(reverse('inventory:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_receive_stock_workflow(self):
        """Test the end-to-end process of receiving new stock for an item."""
        self.assertEqual(Item.objects.get(id=self.item.id).quantity, 10)
        self.assertEqual(ItemLog.objects.count(), 0)

        url = reverse('inventory:adjust_stock', args=[self.section.section_code, self.space.space_code, self.item.item_code, 'RECEIVED'])
        response = self.client.post(url, {'quantity': '5', 'notes': 'New shipment arrived'})
        
        self.assertRedirects(response, self.item.get_absolute_url())
        self.assertEqual(Item.objects.get(id=self.item.id).quantity, 15)
        self.assertEqual(ItemLog.objects.count(), 1)
        log = ItemLog.objects.first()
        self.assertEqual(log.action, 'RECEIVED')
        self.assertEqual(log.quantity_change, 5)

    def test_full_checkout_and_return_workflow(self):
        """Test a complete checkout, check-in, and loan history workflow."""
        # 1. Start a checkout session for the student
        checkout_url = reverse('inventory:checkout_session', args=[self.student.id])
        session = self.client.session
        session['checkout_items'] = {str(self.item.id): 2} 
        session.save()

        # 2. Complete the checkout
        response = self.client.post(checkout_url, {
            'complete_checkout': 'true',
            'due_date_option': 'days',
            'days_to_return': '7',
            'notes': 'Project work',
        })
        self.assertRedirects(response, reverse('inventory:student_detail', args=[self.student.id]))

        # Verify the checkout log was created
        self.assertEqual(CheckoutLog.objects.count(), 1)
        log = CheckoutLog.objects.first()
        self.assertEqual(log.student, self.student)
        self.assertEqual(log.item, self.item)
        self.assertEqual(log.quantity, 2)
        self.assertIsNone(log.return_date)

        # 3. Process a partial return
        check_in_url = reverse('inventory:process_check_in', args=[log.id])
        response = self.client.post(check_in_url, {'quantity_returned': '1'})
        self.assertRedirects(response, reverse('inventory:check_in_page', args=[log.id]))

        # Verify the state after partial return
        log.refresh_from_db()
        self.assertEqual(log.quantity_still_on_loan, 1)
        self.assertIsNone(log.return_date) # Should still be on loan

        # 4. Process the final return
        response = self.client.post(check_in_url, {'quantity_returned': '1'})
        self.assertRedirects(response, reverse('inventory:on_loan_dashboard'))
        
        # Verify the loan is now closed
        log.refresh_from_db()
        self.assertEqual(log.quantity_still_on_loan, 0)
        self.assertIsNotNone(log.return_date)


class RefactoredDataModelTests(TestCase):
    """Tests for the V1.0 club requisition and stock-ledger data model."""

    def setUp(self):
        self.user = User.objects.create_user(username='memberuser', password='password123')
        self.member = ClubMember.objects.create(
            user=self.user,
            member_code='M001',
            name='张三',
            department='宣传部',
        )
        self.section = Section.objects.create(name='宣传物料', section_code=2)
        self.space = Space.objects.create(name='一号储物柜', section=self.section, space_code=2)
        self.item = Item.objects.create(
            name='海报纸',
            space=self.space,
            item_code=2,
            quantity=20,
            unit='包',
            material_type=Item.MaterialType.CONSUMABLE,
            warning_quantity=5,
        )

    def test_item_has_v1_material_attributes(self):
        self.assertEqual(self.item.unit, '包')
        self.assertEqual(self.item.material_type, Item.MaterialType.CONSUMABLE)
        self.assertEqual(self.item.warning_quantity, 5)
        self.assertEqual(self.item.current_stock, 20)
        self.assertEqual(self.item.available_for_issue, 20)
        self.assertFalse(self.item.is_low_stock)

        self.item.quantity = 5
        self.item.save()
        self.assertTrue(self.item.is_low_stock)

    def test_requisition_line_tracks_issue_and_return_quantities(self):
        requisition = Requisition.objects.create(
            member=self.member,
            created_by=self.user,
            purpose='社团活动宣传',
        )
        line = RequisitionItem.objects.create(
            requisition=requisition,
            item=self.item,
            quantity_requested=6,
            quantity_approved=4,
            quantity_issued=4,
        )
        self.assertEqual(line.quantity_still_out, 4)

        line.quantity_returned = 2
        line.full_clean()
        line.save()
        self.assertEqual(line.quantity_still_out, 2)

    def test_requisition_line_cannot_exceed_parent_quantities(self):
        requisition = Requisition.objects.create(member=self.member, purpose='活动')
        line = RequisitionItem(
            requisition=requisition,
            item=self.item,
            quantity_requested=3,
            quantity_approved=4,
        )
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_return_line_links_back_to_requisition_line(self):
        requisition = Requisition.objects.create(member=self.member, purpose='活动')
        requisition_line = RequisitionItem.objects.create(
            requisition=requisition,
            item=self.item,
            quantity_requested=2,
            quantity_approved=2,
            quantity_issued=2,
        )
        return_record = ReturnRecord.objects.create(member=self.member, created_by=self.user)
        return_line = ReturnItem.objects.create(
            return_record=return_record,
            requisition_item=requisition_line,
            quantity=1,
            condition=ReturnItem.Condition.OK,
        )
        self.assertEqual(return_line.requisition_item.item, self.item)
        self.assertEqual(return_line.get_condition_display(), '正常')

    def test_stock_transaction_supports_idempotency_key_and_nonzero_change(self):
        transaction = StockTransaction.objects.create(
            item=self.item,
            transaction_type=StockTransaction.TransactionType.INBOUND,
            quantity_change=10,
            balance_after=30,
            user=self.user,
            reference_type='INITIAL_SETUP',
            source_key='initial:item-2',
            reason='阶段二模型测试',
        )
        self.assertEqual(transaction.quantity_change, 10)
        self.assertEqual(self.item.stock_transactions.count(), 1)

        invalid = StockTransaction(
            item=self.item,
            transaction_type=StockTransaction.TransactionType.ISSUE,
            quantity_change=0,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_inventory_count_difference_is_physical_minus_system(self):
        count = InventoryCount.objects.create(created_by=self.user, notes='首次盘点')
        count_line = InventoryCountItem.objects.create(
            inventory_count=count,
            item=self.item,
            system_quantity=20,
            counted_quantity=18,
            reason='两包材料已损耗',
        )
        self.assertEqual(count_line.difference, -2)


class ServiceWorkflowTests(TestCase):
    """End-to-end tests for atomic issue, return and adjustment services."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='workflow-admin',
            email='admin@example.com',
            password='password123',
        )
        self.member_user = User.objects.create_user(
            username='workflow-member',
            password='password123',
        )
        self.other_user = User.objects.create_user(
            username='workflow-other',
            password='password123',
        )
        self.member = ClubMember.objects.create(
            user=self.member_user,
            member_code='M100',
            name='李四',
        )
        self.section = Section.objects.create(name='活动物资', section_code=10)
        self.space = Space.objects.create(name='二号储物柜', section=self.section, space_code=10)

    def make_item(self, code, quantity, material_type):
        return Item.objects.create(
            name=f'物资{code}',
            space=self.space,
            item_code=code,
            quantity=quantity,
            material_type=material_type,
            warning_quantity=1,
        )

    def make_submitted_requisition(self, item_quantities):
        requisition = create_requisition(
            member=self.member,
            user=self.member_user,
            purpose='社团活动',
        )
        for item, quantity in item_quantities:
            add_requisition_item(
                requisition_id=requisition.id,
                item_id=item.id,
                quantity=quantity,
                user=self.member_user,
            )
        submit_requisition(requisition_id=requisition.id, user=self.member_user)
        approve_requisition(requisition_id=requisition.id, user=self.admin)
        return Requisition.objects.get(id=requisition.id)

    def test_issue_is_atomic_and_idempotent(self):
        item = self.make_item(10, 5, Item.MaterialType.CONSUMABLE)
        requisition = self.make_submitted_requisition([(item, 3)])

        issue_requisition(requisition_id=requisition.id, user=self.admin)
        item.refresh_from_db()
        requisition.refresh_from_db()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(requisition.status, Requisition.Status.COMPLETED)
        self.assertEqual(StockTransaction.objects.filter(
            transaction_type=StockTransaction.TransactionType.ISSUE
        ).count(), 1)

        # A retry after success returns the same completed state without a second deduction.
        issue_requisition(requisition_id=requisition.id, user=self.admin)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(StockTransaction.objects.filter(
            transaction_type=StockTransaction.TransactionType.ISSUE
        ).count(), 1)

    def test_issue_rolls_back_all_lines_when_one_item_is_insufficient(self):
        first = self.make_item(11, 5, Item.MaterialType.CONSUMABLE)
        second = self.make_item(12, 1, Item.MaterialType.CONSUMABLE)
        requisition = self.make_submitted_requisition([(first, 3), (second, 2)])

        with self.assertRaises(InsufficientStockError):
            issue_requisition(requisition_id=requisition.id, user=self.admin)

        first.refresh_from_db()
        second.refresh_from_db()
        requisition.refresh_from_db()
        self.assertEqual(first.quantity, 5)
        self.assertEqual(second.quantity, 1)
        self.assertEqual(requisition.status, Requisition.Status.APPROVED)
        self.assertEqual(StockTransaction.objects.count(), 0)

    def test_reusable_return_updates_stock_and_closes_requisition(self):
        item = self.make_item(13, 5, Item.MaterialType.REUSABLE)
        requisition = self.make_submitted_requisition([(item, 2)])
        issue_requisition(requisition_id=requisition.id, user=self.admin)

        issued_line = RequisitionItem.objects.get(requisition=requisition, item=item)
        first_return = ReturnRecord.objects.create(
            member=self.member,
            created_by=self.member_user,
        )
        ReturnItem.objects.create(
            return_record=first_return,
            requisition_item=issued_line,
            quantity=1,
            condition=ReturnItem.Condition.OK,
        )
        submit_return(return_record_id=first_return.id, user=self.member_user)
        confirm_return(return_record_id=first_return.id, user=self.admin)

        item.refresh_from_db()
        requisition.refresh_from_db()
        self.assertEqual(item.quantity, 4)
        self.assertEqual(requisition.status, Requisition.Status.ISSUED)

        second_return = ReturnRecord.objects.create(member=self.member, created_by=self.member_user)
        ReturnItem.objects.create(
            return_record=second_return,
            requisition_item=issued_line,
            quantity=1,
            condition=ReturnItem.Condition.DAMAGED,
        )
        submit_return(return_record_id=second_return.id, user=self.member_user)
        confirm_return(return_record_id=second_return.id, user=self.admin)

        item.refresh_from_db()
        issued_line.refresh_from_db()
        requisition.refresh_from_db()
        self.assertEqual(item.quantity, 4)
        self.assertEqual(issued_line.quantity_returned, 2)
        self.assertEqual(requisition.status, Requisition.Status.COMPLETED)
        self.assertEqual(StockTransaction.objects.filter(item=item).count(), 4)

    def test_material_edit_form_cannot_overwrite_current_stock(self):
        item = self.make_item(16, 7, Item.MaterialType.CONSUMABLE)
        form = ItemForm(
            data={
                'space': item.space_id,
                'item_code': item.item_code,
                'name': item.name,
                'description': item.description or '演示物资',
                'quantity': 999,
                'unit': item.unit,
                'material_type': item.material_type,
                'warning_quantity': item.warning_quantity,
                'is_active': 'on',
                'buffer_quantity': item.buffer_quantity,
            },
            instance=item,
        )
        self.assertTrue(form.is_valid())
        updated = form.save()
        self.assertEqual(updated.quantity, 7)

    def test_member_cannot_approve_or_edit_another_members_request(self):
        item = self.make_item(14, 5, Item.MaterialType.CONSUMABLE)
        requisition = self.make_submitted_requisition([(item, 1)])

        with self.assertRaises(WorkflowError):
            approve_requisition(requisition_id=requisition.id, user=self.member_user)
        with self.assertRaises(WorkflowError):
            add_requisition_item(
                requisition_id=requisition.id,
                item_id=item.id,
                quantity=1,
                user=self.other_user,
            )

    def test_rejection_requires_reason_and_member_cannot_adjust_stock(self):
        item = self.make_item(18, 4, Item.MaterialType.CONSUMABLE)
        requisition = create_requisition(
            member=self.member,
            user=self.member_user,
            purpose='待驳回申请',
        )
        add_requisition_item(
            requisition_id=requisition.id,
            item_id=item.id,
            quantity=1,
            user=self.member_user,
        )
        submit_requisition(requisition_id=requisition.id, user=self.member_user)

        with self.assertRaises(WorkflowError):
            reject_requisition(
                requisition_id=requisition.id,
                user=self.admin,
                reason=' ',
            )
        requisition.refresh_from_db()
        self.assertEqual(requisition.status, Requisition.Status.SUBMITTED)

        with self.assertRaises(WorkflowError):
            record_stock_adjustment(
                item_id=item.id,
                user=self.member_user,
                action='RECEIVED',
                quantity=2,
                notes='越权调整',
            )
        item.refresh_from_db()
        self.assertEqual(item.quantity, 4)

        reject_requisition(
            requisition_id=requisition.id,
            user=self.admin,
            reason='活动时间未确定',
        )
        requisition.refresh_from_db()
        self.assertEqual(requisition.status, Requisition.Status.REJECTED)
        self.assertEqual(requisition.reject_reason, '活动时间未确定')

    def test_manual_adjustment_writes_new_and_legacy_ledgers(self):
        item = self.make_item(15, 2, Item.MaterialType.CONSUMABLE)
        record_stock_adjustment(
            item_id=item.id,
            user=self.admin,
            action='RECEIVED',
            quantity=3,
            notes='补充活动库存',
        )
        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)
        self.assertEqual(item.stock_transactions.count(), 1)
        self.assertEqual(item.logs.count(), 1)

    def test_inventory_count_reconciles_stock_and_is_idempotent(self):
        item = self.make_item(17, 8, Item.MaterialType.CONSUMABLE)
        count = create_inventory_count(user=self.admin, notes='活动结束后盘点')
        line = InventoryCountItem.objects.get(inventory_count=count, item=item)
        line.counted_quantity = 6
        line.reason = '使用损耗'
        line.save(update_fields=['counted_quantity', 'reason'])

        confirm_inventory_count(count_id=count.id, user=self.admin)
        item.refresh_from_db()
        count.refresh_from_db()
        self.assertEqual(item.quantity, 6)
        self.assertEqual(count.status, InventoryCount.Status.CONFIRMED)
        self.assertEqual(StockTransaction.objects.filter(
            reference_type='INVENTORY_COUNT_ITEM'
        ).count(), 1)

        confirm_inventory_count(count_id=count.id, user=self.admin)
        self.assertEqual(StockTransaction.objects.filter(
            reference_type='INVENTORY_COUNT_ITEM'
        ).count(), 1)

    def test_inventory_count_rejects_stale_snapshot(self):
        item = self.make_item(19, 8, Item.MaterialType.CONSUMABLE)
        count = create_inventory_count(user=self.admin, notes='防止过期盘点覆盖新库存')
        line = InventoryCountItem.objects.get(inventory_count=count, item=item)
        line.counted_quantity = 6
        line.save(update_fields=['counted_quantity'])

        record_stock_adjustment(
            item_id=item.id,
            user=self.admin,
            action='RECEIVED',
            quantity=1,
            notes='盘点期间入库',
        )
        with self.assertRaises(WorkflowError):
            confirm_inventory_count(count_id=count.id, user=self.admin)

        item.refresh_from_db()
        count.refresh_from_db()
        self.assertEqual(item.quantity, 9)
        self.assertEqual(count.status, InventoryCount.Status.DRAFT)
        self.assertEqual(
            StockTransaction.objects.filter(reference_type='INVENTORY_COUNT_ITEM').count(),
            0,
        )

    def test_consumable_return_is_rejected_without_stock_change(self):
        item = self.make_item(20, 5, Item.MaterialType.CONSUMABLE)
        requisition = self.make_submitted_requisition([(item, 2)])
        issue_requisition(requisition_id=requisition.id, user=self.admin)
        issued_line = RequisitionItem.objects.get(requisition=requisition, item=item)

        return_record = ReturnRecord.objects.create(
            member=self.member,
            created_by=self.member_user,
        )
        ReturnItem.objects.create(
            return_record=return_record,
            requisition_item=issued_line,
            quantity=1,
            condition=ReturnItem.Condition.OK,
        )
        submit_return(return_record_id=return_record.id, user=self.member_user)
        with self.assertRaises(WorkflowError):
            confirm_return(return_record_id=return_record.id, user=self.admin)

        item.refresh_from_db()
        return_record.refresh_from_db()
        self.assertEqual(item.quantity, 3)
        self.assertEqual(return_record.status, ReturnRecord.Status.SUBMITTED)


class CoreWorkflowViewTests(TestCase):
    """Smoke tests for the V1.0 member and administrator pages."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='view-admin', email='admin@example.com', password='password123'
        )
        self.member_user = User.objects.create_user(
            username='view-member', password='password123'
        )
        self.member = ClubMember.objects.create(
            user=self.member_user, member_code='VIEW-MEMBER', name='页面测试成员'
        )
        self.section = Section.objects.create(name='页面测试分类', section_code=20)
        self.space = Space.objects.create(
            name='页面测试位置', section=self.section, space_code=20
        )
        self.item = Item.objects.create(
            name='页面测试物资', space=self.space, item_code=20, quantity=5,
            material_type=Item.MaterialType.CONSUMABLE,
        )

    def test_member_can_submit_and_admin_can_issue_requisition(self):
        self.client.force_login(self.member_user)
        response = self.client.post(reverse('inventory:requisition_create'), {
            'member': self.member.id,
            'purpose': '页面回归测试',
            'notes': '',
            'planned_return_date': '',
        })
        self.assertEqual(response.status_code, 302)
        requisition = Requisition.objects.get(member=self.member)

        self.client.post(
            reverse('inventory:requisition_add_line', args=[requisition.request_no]),
            {'item': self.item.id, 'quantity_requested': 2, 'notes': ''},
        )
        self.client.post(reverse('inventory:requisition_submit', args=[requisition.request_no]))
        requisition.refresh_from_db()
        self.assertEqual(requisition.status, Requisition.Status.SUBMITTED)

        self.client.force_login(self.admin)
        self.client.post(reverse('inventory:requisition_approve', args=[requisition.request_no]))
        self.client.post(reverse('inventory:requisition_issue', args=[requisition.request_no]))
        requisition.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(requisition.status, Requisition.Status.COMPLETED)
        self.assertEqual(self.item.quantity, 3)

    def test_admin_can_create_and_confirm_inventory_count_page(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('inventory:inventory_count_create'), {
            'notes': '页面盘点测试',
        })
        self.assertEqual(response.status_code, 302)
        count = InventoryCount.objects.get()
        line = InventoryCountItem.objects.get(inventory_count=count, item=self.item)

        response = self.client.get(
            reverse('inventory:inventory_count_detail', args=[count.count_no])
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('inventory:inventory_count_detail', args=[count.count_no]),
            {f'counted_{line.id}': '4', f'reason_{line.id}': '少一件'},
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        count.refresh_from_db()
        self.assertEqual(self.item.quantity, 4)
        self.assertEqual(count.status, InventoryCount.Status.CONFIRMED)

    def test_member_is_redirected_from_admin_inventory_mutations(self):
        self.client.force_login(self.member_user)
        response = self.client.get(reverse(
            'inventory:item_update',
            args=[self.section.section_code, self.space.space_code, self.item.item_code],
        ))
        self.assertRedirects(response, reverse('inventory:dashboard'))
        self.assertRedirects(
            self.client.get(reverse('inventory:inventory_count_list')),
            reverse('inventory:dashboard'),
        )
        self.assertRedirects(
            self.client.get(reverse('inventory:checkout_find_student')),
            reverse('inventory:dashboard'),
        )

    def test_member_requisition_list_is_scoped_to_current_member(self):
        other_user = User.objects.create_user(username='other-view-member', password='password123')
        other_member = ClubMember.objects.create(
            user=other_user,
            member_code='OTHER-MEMBER',
            name='其他成员',
        )
        Requisition.objects.create(
            member=self.member,
            created_by=self.member_user,
            purpose='当前成员可见申请',
        )
        Requisition.objects.create(
            member=other_member,
            created_by=other_user,
            purpose='其他成员不可见申请',
        )

        self.client.force_login(self.member_user)
        response = self.client.get(reverse('inventory:requisition_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '当前成员可见申请')
        self.assertNotContains(response, '其他成员不可见申请')

    def test_admin_item_creation_records_initial_stock(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('inventory:item_create', args=[self.section.section_code, self.space.space_code]),
            {
                'space': self.space.id,
                'item_code': 21,
                'name': '新增测试物资',
                'description': '用于页面回归',
                'quantity': 9,
                'unit': '个',
                'material_type': Item.MaterialType.REUSABLE,
                'warning_quantity': 2,
                'is_active': 'on',
                'buffer_quantity': 0,
            },
        )
        self.assertEqual(response.status_code, 302)
        item = Item.objects.get(item_code=21, space=self.space)
        transaction = StockTransaction.objects.get(item=item)
        self.assertEqual(transaction.transaction_type, StockTransaction.TransactionType.INITIAL)
        self.assertEqual(transaction.quantity_change, 9)
        self.assertEqual(transaction.balance_after, 9)
