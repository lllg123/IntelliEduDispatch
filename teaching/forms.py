from django import forms

from .models import TeachingRequest, TeachingResource


class TeachingResourceForm(forms.ModelForm):
    class Meta:
        model = TeachingResource
        fields = ['name', 'code', 'kind', 'location', 'capacity', 'features', 'description', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class TeachingRequestForm(forms.ModelForm):
    class Meta:
        model = TeachingRequest
        fields = ['title', 'course', 'start_at', 'end_at', 'expected_attendees',
                  'resource_kind', 'required_features', 'notes']
        widgets = {
            'start_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_at')
        end = cleaned.get('end_at')
        if start and end and end <= start:
            self.add_error('end_at', '结束时间必须晚于开始时间。')
        return cleaned
