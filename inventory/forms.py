# sherlock-python/inventory/forms.py

from django import forms
from .models import Section
from .models import Space
from .models import Item
from .models import Student
from .models import UserProfile
from .models import ClubMember
from .models import Requisition
from .models import RequisitionItem
from .models import ReturnRecord
from .models import ReturnItem
from .models import InventoryCount
from .models import InventoryCountItem
from django.contrib.auth.models import User

class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ['section_code', 'name', 'description']
        labels = {
            'section_code': 'Section Code',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['section_code'].disabled = True

class SpaceForm(forms.ModelForm):
    class Meta:
        model = Space
        fields = ['section', 'space_code', 'name', 'description']
        labels = {
            'space_code': 'Space Code',
            'section': 'Parent Section'
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['space_code'].disabled = True

class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            'space',
            'item_code',
            'name',
            'description',
            'quantity',
            'unit',
            'material_type',
            'warning_quantity',
            'is_active',
            'buffer_quantity',
        ]
        labels = {
            'item_code': '物资编码',
            'space': '存放位置',
            'quantity': '当前库存（新建时填写）',
            'unit': '计量单位',
            'material_type': '物资类型',
            'warning_quantity': '库存预警阈值',
            'is_active': '启用状态',
            'buffer_quantity': '借用安全库存（兼容旧流程）',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['item_code'].disabled = True
            # Inventory is changed only through transactional stock services,
            # never by ordinary material profile editing.
            self.fields['quantity'].disabled = True

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['admission_number', 'name', 'student_class', 'section']
        labels = {
            'admission_number': 'Admission Number',
            'student_class': 'Class',
        }

class StockAdjustmentForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        label="Quantity Change",
        widget=forms.NumberInput(attrs={'autofocus': True})
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=True,
        help_text="Please provide a reason for this stock change (e.g., 'New order received', 'Dropped and damaged')."
    )

class UserUpdateForm(forms.ModelForm):
    """Form for users to update their own basic information."""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

class UserRoleForm(forms.ModelForm):
    """Form for Admins to update a user's role."""
    class Meta:
        model = UserProfile
        fields = ['role']


class ClubMemberForm(forms.ModelForm):
    class Meta:
        model = ClubMember
        fields = ['user', 'member_code', 'name', 'department', 'contact', 'is_active']
        labels = {
            'user': '登录账号',
            'member_code': '成员编号',
            'department': '部门或职务',
            'contact': '联系方式',
            'is_active': '启用状态',
        }


class RequisitionForm(forms.ModelForm):
    class Meta:
        model = Requisition
        fields = ['member', 'purpose', 'notes', 'planned_return_date']
        labels = {
            'member': '申请成员',
            'purpose': '领用用途',
            'notes': '备注',
            'planned_return_date': '计划归还时间',
        }
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
            'planned_return_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class RequisitionItemForm(forms.ModelForm):
    class Meta:
        model = RequisitionItem
        fields = ['item', 'quantity_requested', 'notes']
        labels = {
            'item': '物资',
            'quantity_requested': '申请数量',
            'notes': '明细备注',
        }
        widgets = {
            'quantity_requested': forms.NumberInput(attrs={
                'min': 1,
                'class': 'quantity-input',
            }),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class ReturnRecordForm(forms.ModelForm):
    class Meta:
        model = ReturnRecord
        fields = ['member', 'notes']
        labels = {
            'member': '归还成员',
            'notes': '备注',
        }
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class ReturnItemForm(forms.ModelForm):
    class Meta:
        model = ReturnItem
        fields = ['requisition_item', 'quantity', 'condition', 'notes']
        labels = {
            'requisition_item': '原出库明细',
            'quantity': '归还数量',
            'condition': '物资状态',
            'notes': '明细备注',
        }
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class InventoryCountForm(forms.ModelForm):
    class Meta:
        model = InventoryCount
        fields = ['notes']
        labels = {
            'notes': '盘点说明',
        }
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class InventoryCountItemForm(forms.ModelForm):
    class Meta:
        model = InventoryCountItem
        fields = ['item', 'system_quantity', 'counted_quantity', 'reason']
        labels = {
            'item': '物资',
            'system_quantity': '系统库存',
            'counted_quantity': '实盘数量',
            'reason': '差异原因',
        }
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 2}),
        }
