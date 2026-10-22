# sherlock-python/inventory/models.py

from django.db import models
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum
from django.db.models.signals import post_save
from datetime import timedelta
import uuid

import barcode
from barcode.writer import SVGWriter
import qrcode
import qrcode.image.svg

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        abstract = True 

class Section(TimeStampedModel):
    section_code = models.PositiveIntegerField(
        unique=True,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(9999)
        ],
        help_text="A unique 4-digit code for this section (1-9999)."
    )
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=100)
    
    search_entry = GenericRelation('SearchEntry', object_id_field='object_id', content_type_field='content_type')

    def __str__(self):
        return f"{self.name} (Section: {self.section_code})"
    
    def get_absolute_url(self):
        return reverse('inventory:section_detail', kwargs={'section_code': self.section_code})

    def generate_qr_code_svg(self):
        """Generates the QR code SVG content, replicating the Rails logic."""
        padded_name = (self.name + '*' * 50)[:50]
        padded_desc = (self.description + '*' * 100)[:100]
        
        qr_data = (
            f"SHERLOCK;SECTIONCODE:{str(self.section_code).zfill(4)};;"
            f"RESTOREDATA;NAME:{padded_name};DESCRIPTION:{padded_desc};;"
        )
        
        img = qrcode.make(qr_data, image_factory=qrcode.image.svg.SvgPathImage)
        return img.to_string(encoding='unicode')

class Space(TimeStampedModel):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='spaces')
    space_code = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(9999)],
        help_text="A 4-digit code for this space, unique within its section (1-9999)."
    )
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=100)
    
    original_section_code = models.PositiveIntegerField(editable=False, null=True)
    
    search_entry = GenericRelation('SearchEntry')

    class Meta:
        unique_together = ('section', 'space_code')

    def __str__(self):
        return f"{self.name} (in {self.section.name})"

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.original_section_code = self.section.section_code
        super().save(*args, **kwargs)
        
    def get_absolute_url(self):
        return reverse('inventory:space_detail', kwargs={'section_code': self.section.section_code, 'space_code': self.space_code})

    def generate_qr_code_svg(self):
        """Generates the QR code SVG content using the permanent original code."""
        padded_name = (self.name + '*' * 50)[:50]
        padded_desc = (self.description + '*' * 100)[:100]
        

        qr_data = (
            f"SHERLOCK;SECTIONCODE:{str(self.original_section_code).zfill(4)};"
            f"SPACECODE:{str(self.space_code).zfill(4)};;"
            f"RESTOREDATA;NAME:{padded_name};DESCRIPTION:{padded_desc};;"
        )
        
        img = qrcode.make(qr_data, image_factory=qrcode.image.svg.SvgPathImage)
        return img.to_string(encoding='unicode')

class Item(TimeStampedModel):
    class MaterialType(models.TextChoices):
        CONSUMABLE = 'CONSUMABLE', '耗材'
        REUSABLE = 'REUSABLE', '可重复使用物资'

    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name='items')
    item_code = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(9999)],
        help_text="A 4-digit code for this item, unique within its space (1-9999)."
    )
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Current quantity of this material in inventory."
    )
    buffer_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Minimum quantity to keep in stock. This amount cannot be checked out."
    )
    unit = models.CharField(
        max_length=20,
        default='个',
        help_text="Fixed unit for this material, such as 个、包 or 卷."
    )
    material_type = models.CharField(
        max_length=20,
        choices=MaterialType.choices,
        default=MaterialType.REUSABLE,
        help_text="Consumables are issued directly; reusable materials can be returned."
    )
    warning_quantity = models.PositiveIntegerField(
        default=5,
        help_text="Show a low-stock warning when the current quantity is at or below this value."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive materials remain visible in history but cannot be selected for new requests."
    )
    barcode = models.CharField(max_length=13, blank=True, editable=False, unique=True, null=True)
    original_section_code = models.PositiveIntegerField(editable=False, null=True)
    original_space_code = models.PositiveIntegerField(editable=False, null=True)
    search_entry = GenericRelation('SearchEntry', object_id_field='object_id', content_type_field='content_type')

    class Meta:
        unique_together = ('space', 'item_code')

    def __str__(self):
        return f"{self.name} (Qty: {self.quantity})"

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.original_section_code = self.space.section.section_code
            self.original_space_code = self.space.space_code
        
        base_code = (
            f"{self.original_section_code:04d}"
            f"{self.original_space_code:04d}"
            f"{self.item_code:04d}"
        )
        
        EAN = barcode.get_barcode_class('ean13')
        ean_barcode = EAN(base_code)
        
        self.barcode = ean_barcode.get_fullcode()
        super().save(*args, **kwargs)

        search_entry, created = SearchEntry.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(self),
            object_id=self.id
        )
        search_entry.name = self.name
        search_entry.url = self.get_absolute_url()
        search_entry.save()
    
    def get_absolute_url(self):
        return reverse('inventory:item_detail', kwargs={
            'section_code': self.space.section.section_code,
            'space_code': self.space.space_code,
            'item_code': self.item_code
        })

    def generate_barcode_svg(self):
        """Generates the EAN-13 barcode SVG content using the permanent barcode field."""
        EAN = barcode.get_barcode_class('ean13')
        ean_barcode = EAN(self.barcode, writer=SVGWriter())
        return ean_barcode.render().decode('utf-8')
    
    @property
    def checked_out_quantity(self):
        """Calculates the total quantity of this item currently on loan."""
        checked_out = self.checkout_logs.filter(return_date__isnull=True).aggregate(total=Sum('quantity'))['total']
        return checked_out or 0
    
    @property
    def available_quantity(self):
        """Calculates the quantity available for checkout (total - checked out - buffer)."""
        return self.quantity - self.checked_out_quantity - self.buffer_quantity

    @property
    def is_low_stock(self):
        """Whether the material is at or below its configured warning threshold."""
        return self.current_stock <= self.warning_quantity

    @property
    def current_stock(self):
        """The on-hand quantity used by the V1.0 stock ledger."""
        return self.quantity

    @property
    def available_for_issue(self):
        """Quantity available to issue under the new consumable/reusable semantics."""
        # New requisition workflows use quantity as the on-hand balance for
        # both material types. The legacy available_quantity property remains
        # for the old checkout screens until they are migrated in phase 4.
        return self.current_stock


class ClubMember(TimeStampedModel):
    """A club member who can submit material requisitions."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='club_member',
        help_text="Optional login account associated with this member record."
    )
    member_code = models.CharField(max_length=30, unique=True, help_text="Unique club member code.")
    name = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    contact = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name', 'member_code']

    def __str__(self):
        return f"{self.name} ({self.member_code})"


class Requisition(TimeStampedModel):
    """A member's material requisition and its approval lifecycle."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', '草稿'
        SUBMITTED = 'SUBMITTED', '待审批'
        APPROVED = 'APPROVED', '已批准'
        REJECTED = 'REJECTED', '已驳回'
        ISSUED = 'ISSUED', '已出库'
        COMPLETED = 'COMPLETED', '已完成'
        CANCELLED = 'CANCELLED', '已撤回'

    request_no = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    member = models.ForeignKey(
        ClubMember,
        on_delete=models.PROTECT,
        related_name='requisitions'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_requisitions'
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    purpose = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    reject_reason = models.TextField(blank=True)
    planned_return_date = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['member', '-created_at']),
        ]

    def __str__(self):
        return f"领用申请 {str(self.request_no)[:8]} - {self.member.name}"

    @property
    def is_editable(self):
        return self.status == self.Status.DRAFT


class RequisitionItem(models.Model):
    """One requested material and its approved, issued and returned quantities."""

    requisition = models.ForeignKey(Requisition, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='requisition_lines')
    quantity_requested = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    quantity_approved = models.PositiveIntegerField(default=0)
    quantity_issued = models.PositiveIntegerField(default=0)
    quantity_returned = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity_requested__gt=0),
                name='requisition_item_requested_positive'
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_approved__lte=models.F('quantity_requested')),
                name='requisition_item_approved_lte_requested'
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_issued__lte=models.F('quantity_approved')),
                name='requisition_item_issued_lte_approved'
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_returned__lte=models.F('quantity_issued')),
                name='requisition_item_returned_lte_issued'
            ),
        ]
        constraints += [
            models.UniqueConstraint(
                fields=['requisition', 'item'],
                name='unique_requisition_item'
            )
        ]

    def __str__(self):
        return f"{self.item.name} x {self.quantity_requested}"

    @property
    def quantity_still_out(self):
        return self.quantity_issued - self.quantity_returned


class ReturnRecord(TimeStampedModel):
    """A return submission for reusable materials issued to a member."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', '草稿'
        SUBMITTED = 'SUBMITTED', '待验收'
        CONFIRMED = 'CONFIRMED', '已确认'
        REJECTED = 'REJECTED', '已驳回'
        CANCELLED = 'CANCELLED', '已撤回'

    return_no = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    member = models.ForeignKey(ClubMember, on_delete=models.PROTECT, related_name='return_records')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_return_records'
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_return_records'
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"归还单 {str(self.return_no)[:8]} - {self.member.name}"


class ReturnItem(models.Model):
    """A returned quantity linked to an issued requisition line."""

    class Condition(models.TextChoices):
        OK = 'OK', '正常'
        DAMAGED = 'DAMAGED', '损坏'
        LOST = 'LOST', '遗失'

    return_record = models.ForeignKey(ReturnRecord, on_delete=models.CASCADE, related_name='lines')
    requisition_item = models.ForeignKey(
        RequisitionItem,
        on_delete=models.PROTECT,
        related_name='return_lines'
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    condition = models.CharField(max_length=10, choices=Condition.choices, default=Condition.OK)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='return_item_quantity_positive'
            ),
            models.UniqueConstraint(
                fields=['return_record', 'requisition_item'],
                name='unique_return_record_item'
            ),
        ]

    def __str__(self):
        return f"{self.requisition_item.item.name} x {self.quantity}"


class StockTransaction(models.Model):
    """The append-only ledger for every material quantity change."""

    class TransactionType(models.TextChoices):
        INITIAL = 'INITIAL', '初始库存'
        INBOUND = 'INBOUND', '入库'
        ISSUE = 'ISSUE', '领用出库'
        RETURN = 'RETURN', '归还入库'
        DAMAGED = 'DAMAGED', '损坏'
        LOST = 'LOST', '遗失'
        ADJUST_ADD = 'ADJUST_ADD', '盘点增加'
        ADJUST_SUB = 'ADJUST_SUB', '盘点减少'

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='stock_transactions')
    transaction_type = models.CharField(max_length=12, choices=TransactionType.choices)
    quantity_change = models.IntegerField(help_text="Positive for inbound stock and negative for outbound stock.")
    balance_after = models.PositiveIntegerField(null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_transactions'
    )
    reference_type = models.CharField(max_length=30, blank=True)
    reference_id = models.PositiveBigIntegerField(null=True, blank=True)
    source_key = models.CharField(
        max_length=120,
        unique=True,
        null=True,
        blank=True,
        help_text="Deterministic key used to make a business operation idempotent."
    )
    reason = models.TextField(blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_at', '-id']
        indexes = [
            models.Index(fields=['item', '-occurred_at']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity_change=0),
                name='stock_transaction_change_nonzero'
            ),
        ]

    def __str__(self):
        sign = '+' if self.quantity_change > 0 else ''
        return f"{self.item.name}: {sign}{self.quantity_change} ({self.get_transaction_type_display()})"


class InventoryCount(TimeStampedModel):
    """A stock count session used to reconcile physical and recorded quantities."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', '草稿'
        CONFIRMED = 'CONFIRMED', '已确认'
        CANCELLED = 'CANCELLED', '已取消'

    count_no = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_inventory_counts'
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_inventory_counts'
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"盘点单 {str(self.count_no)[:8]}"


class InventoryCountItem(models.Model):
    """The recorded and physically counted quantities for one material."""

    inventory_count = models.ForeignKey(InventoryCount, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='inventory_count_lines')
    system_quantity = models.PositiveIntegerField()
    counted_quantity = models.PositiveIntegerField()
    reason = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['inventory_count', 'item'],
                name='unique_inventory_count_item'
            ),
        ]

    def __str__(self):
        return f"{self.item.name}: {self.system_quantity} -> {self.counted_quantity}"

    @property
    def difference(self):
        return self.counted_quantity - self.system_quantity
    
class PrintQueue(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return f"Print Queue for {self.user.username}"

class PrintQueueItem(models.Model):
    print_queue = models.ForeignKey(PrintQueue, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    
    print_content = models.TextField()
    item_hash = models.CharField(max_length=64)

    def __str__(self):
        return f"{self.quantity}x {self.name} in {self.print_queue}"

class SearchEntry(models.Model):
    name = models.CharField(max_length=255)
    url = models.CharField(max_length=500) 

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    searchable_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        unique_together = ('content_type', 'object_id')

    def __str__(self):
        return f"Search entry for '{self.name}'"
    
class Student(TimeStampedModel):
    """A record for a student who can borrow items."""
    admission_number = models.CharField(max_length=50, unique=True, help_text="Unique student admission or ID number.")
    name = models.CharField(max_length=100)
    student_class = models.CharField(max_length=50, verbose_name="Class")
    section = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.name} ({self.admission_number})"
    
    def save(self, *args, **kwargs):
        self.name = self.name.upper()
        self.admission_number = self.admission_number.upper()
        self.student_class = self.student_class.upper()
        self.section = self.section.upper()
        
        super().save(*args, **kwargs)

class UserProfile(models.Model):
    """Extends the default Django User model to include a role and activity tracking."""
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        MEMBER = 'MEMBER', 'Member'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    last_seen = models.DateTimeField(null=True, blank=True, help_text="The last time the user made a request.")

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @property
    def is_online(self):
        """
        Determines if the user is 'online' based on their last seen time.
        A user is considered online if they were active in the last 5 minutes.
        """
        if not self.last_seen:
            return False
        return timezone.now() < self.last_seen + timedelta(minutes=5)

def create_user_profile(sender, instance, created, **kwargs):
    if created:
        role = UserProfile.Role.ADMIN if instance.is_superuser else UserProfile.Role.MEMBER
        UserProfile.objects.create(user=instance, role=role)

post_save.connect(create_user_profile, sender=settings.AUTH_USER_MODEL)

class CheckoutLog(models.Model):
    """A record of an item being checked out by a student."""
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="checkout_logs")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="checkout_logs")
    checkout_date = models.DateTimeField(auto_now_add=True)
    return_date = models.DateTimeField(null=True, blank=True, help_text="This is set when the item is returned.")
    due_date = models.DateTimeField(help_text="The date and time the item is expected to be returned.")
    notes = models.TextField(blank=True, help_text="Reason or notes for this checkout.")
    
    quantity = models.PositiveIntegerField(default=1, help_text="The number of items checked out in this transaction.")

    def __str__(self):
        status = "Returned" if self.return_date else "On Loan"
        return f"{self.item.name} to {self.student.name} ({status})"
    
    @property
    def quantity_returned_so_far(self):
        """Calculates the total quantity returned for this specific checkout log."""
        returned = self.check_in_logs.aggregate(total=Sum('quantity_returned'))['total']
        return returned or 0
    
    @property
    def quantity_still_on_loan(self):
        """Calculates the quantity still on loan for this checkout."""
        return self.quantity - self.quantity_returned_so_far
    
    @property
    def is_overdue(self):
        """Returns True if the item is not returned and the due date is in the past."""
        return self.return_date is None and self.due_date < timezone.now()
    
class CheckInLog(models.Model):
    """A record of a partial or full return for a specific checkout."""
    class Condition(models.TextChoices):
        OK = 'OK', 'OK'
        DAMAGED = 'DAMAGED', 'Damaged'

    checkout_log = models.ForeignKey(CheckoutLog, on_delete=models.CASCADE, related_name="check_in_logs")
    quantity_returned = models.PositiveIntegerField()
    return_date = models.DateTimeField(auto_now_add=True)
    
    condition = models.CharField(
        max_length=10, 
        choices=Condition.choices, 
        default=Condition.OK,
        help_text="The condition of the item upon return."
    )

    def __str__(self):
        return f"{self.quantity_returned} units of {self.checkout_log.item.name} returned on {self.return_date.strftime('%Y-%m-%d')} (Condition: {self.get_condition_display()})"

class ItemLog(models.Model):
    """A permanent record of a change in an item's stock quantity."""
    class Action(models.TextChoices):
        RECEIVED = 'RECEIVED', 'Received New Stock'
        DAMAGED = 'DAMAGED', 'Reported Damaged'
        LOST = 'LOST', 'Reported Lost'
        CORRECTION_ADD = 'CORR_ADD', 'Manual Correction (Add)'
        CORRECTION_SUB = 'CORR_SUB', 'Manual Correction (Subtract)'

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="item_logs")
    action = models.CharField(max_length=10, choices=Action.choices)
    
    quantity_change = models.IntegerField()
    
    notes = models.TextField(blank=True, help_text="Reason for the stock change.")
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        sign = '+' if self.quantity_change > 0 else ''
        return f"{sign}{self.quantity_change} of {self.item.name}: {self.get_action_display()} by {self.user.username if self.user else 'Unknown'}"
