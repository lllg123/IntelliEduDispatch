import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import SchedulingRecommendation, TeachingRequest, TeachingResource
from .services import SchedulingError, confirm_schedule, create_recommendation, interpret_requirement, ranked_candidates


class TeachingSchedulingTests(TestCase):
    def setUp(self):
        no_llm = patch.dict('os.environ', {
            'TEACHING_LLM_BASE_URL': '',
            'TEACHING_LLM_API_KEY': '',
            'TEACHING_LLM_MODEL': '',
        })
        no_llm.start()
        self.addCleanup(no_llm.stop)
        self.admin = User.objects.create_superuser('scheduler', 'scheduler@example.com', 'password123')
        self.teacher = User.objects.create_user('teacher', password='password123')
        self.other = User.objects.create_user('otherteacher', password='password123')
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=2)
        self.room = TeachingResource.objects.create(
            name='智慧教室 A', code='ROOM-A', kind=TeachingResource.Kind.CLASSROOM,
            capacity=35, features='投影,录播', location='教学楼 201',
        )
        self.room_b = TeachingResource.objects.create(
            name='智慧教室 B', code='ROOM-B', kind=TeachingResource.Kind.CLASSROOM,
            capacity=70, features='投影,录播', location='教学楼 305',
        )
        self.demand = TeachingRequest.objects.create(
            requested_by=self.teacher, title='研讨课', course='数据结构',
            start_at=self.start, end_at=self.start + timedelta(hours=2),
            expected_attendees=30, resource_kind=TeachingResource.Kind.CLASSROOM,
            required_features='投影，录播',
        )

    def test_rule_recommendation_respects_capacity_features_and_conflict(self):
        advice = create_recommendation(demand=self.demand, user=self.teacher)
        self.assertEqual(advice.mode, SchedulingRecommendation.Mode.RULES)
        self.assertEqual(advice.suggested_resource, self.room)
        self.assertEqual([row['resource_id'] for row in advice.candidates], [self.room.pk, self.room_b.pk])

        confirm_schedule(demand_id=self.demand.pk, resource_id=self.room.pk, user=self.admin)
        second = TeachingRequest.objects.create(
            requested_by=self.other, title='实践课', course='数据库',
            start_at=self.start + timedelta(hours=1), end_at=self.start + timedelta(hours=3),
            expected_attendees=30, resource_kind=TeachingResource.Kind.CLASSROOM,
            required_features='录播',
        )
        self.assertEqual([row['resource_id'] for row in ranked_candidates(second)], [self.room_b.pk])

    def test_stale_advice_cannot_double_book_resource(self):
        create_recommendation(demand=self.demand, user=self.teacher)
        second = TeachingRequest.objects.create(
            requested_by=self.other, title='同期课程', course='操作系统',
            start_at=self.start, end_at=self.start + timedelta(hours=1),
            expected_attendees=30, resource_kind=TeachingResource.Kind.CLASSROOM,
        )
        confirm_schedule(demand_id=second.pk, resource_id=self.room.pk, user=self.admin)
        with self.assertRaises(SchedulingError):
            confirm_schedule(demand_id=self.demand.pk, resource_id=self.room.pk, user=self.admin)
        self.demand.refresh_from_db()
        self.assertEqual(self.demand.status, TeachingRequest.Status.PENDING)
        self.assertIsNone(self.demand.assigned_resource)

    def test_no_candidate_explains_conflict_and_suggests_other_day(self):
        TeachingResource.objects.filter(pk=self.room_b.pk).update(is_active=False)
        occupied = TeachingRequest.objects.create(
            requested_by=self.other, title='占用', course='英语',
            start_at=self.start, end_at=self.start + timedelta(hours=2),
            expected_attendees=10, resource_kind=TeachingResource.Kind.CLASSROOM,
        )
        confirm_schedule(demand_id=occupied.pk, resource_id=self.room.pk, user=self.admin)
        advice = create_recommendation(demand=self.demand, user=self.teacher)
        self.assertIsNone(advice.suggested_resource)
        self.assertEqual(advice.candidates, [])
        self.assertTrue(advice.alternatives)
        self.assertEqual(advice.alternatives[0]['resource_id'], self.room.pk)

    @patch.dict('os.environ', {
        'TEACHING_LLM_BASE_URL': 'https://llm.example/v1',
        'TEACHING_LLM_API_KEY': 'test-key',
        'TEACHING_LLM_MODEL': 'test-model',
    })
    @patch('teaching.services.http_request.urlopen')
    def test_llm_selects_only_from_eligible_candidates(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            'choices': [{'message': {'content': json.dumps({
                'resource_id': self.room_b.pk,
                'reason': '更适合分组教学和后续扩展。',
            }, ensure_ascii=False)}}]
        }).encode('utf-8')
        urlopen.return_value.__enter__.return_value = response
        advice = create_recommendation(demand=self.demand, user=self.teacher)
        self.assertEqual(advice.mode, SchedulingRecommendation.Mode.LLM)
        self.assertEqual(advice.suggested_resource, self.room_b)
        self.assertEqual(advice.llm_model, 'test-model')

        response.read.return_value = json.dumps({
            'choices': [{'message': {'content': json.dumps({
                'resource_id': 99999,
                'reason': '越权候选',
            }, ensure_ascii=False)}}]
        }).encode('utf-8')
        fallback = create_recommendation(demand=self.demand, user=self.teacher)
        self.assertEqual(fallback.mode, SchedulingRecommendation.Mode.RULES)
        self.assertEqual(fallback.suggested_resource, self.room)

    @patch.dict('os.environ', {
        'TEACHING_LLM_BASE_URL': 'https://llm.example/v1',
        'TEACHING_LLM_API_KEY': 'test-key',
        'TEACHING_LLM_MODEL': 'test-model',
    })
    @patch('teaching.services.http_request.urlopen')
    def test_ai_extracts_reviewable_requirements_without_auto_booking(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            'choices': [{'message': {'content': json.dumps({
                'course': '数据结构', 'title': '专题研讨', 'resource_kind': 'CLASSROOM',
                'expected_attendees': 30, 'required_features': ['投影', '录播'],
            }, ensure_ascii=False)}}]
        }).encode('utf-8')
        urlopen.return_value.__enter__.return_value = response
        self.client.force_login(self.teacher)
        page = self.client.post(reverse('teaching:request_assistant'), {
            'description': '30 人的数据结构专题研讨，需要投影和录播教室。',
        })
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '核对并补全需求')
        self.assertContains(page, '数据结构')
        self.assertEqual(TeachingRequest.objects.count(), 1)
        self.assertEqual(interpret_requirement('需要 30 人教室')['expected_attendees'], 30)

    def test_service_disallows_member_confirmation(self):
        with self.assertRaises(SchedulingError):
            confirm_schedule(demand_id=self.demand.pk, resource_id=self.room.pk, user=self.teacher)
        self.demand.refresh_from_db()
        self.assertEqual(self.demand.status, TeachingRequest.Status.PENDING)

    def test_teacher_cannot_manage_resources_or_confirm_or_view_others(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('teaching:request_detail', args=[self.demand.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('teaching:resource_create')).status_code, 403)
        self.assertEqual(self.client.post(reverse('teaching:confirm', args=[self.demand.pk]), {'resource_id': self.room.pk}).status_code, 403)
        self.assertNotContains(self.client.get(reverse('teaching:request_list')), '数据结构')

    def test_page_workflow_and_cancel_releases_slot(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('teaching:recommend', args=[self.demand.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse('teaching:request_detail', args=[self.demand.pk])), '智慧教室 A')
        self.client.force_login(self.admin)
        response = self.client.post(reverse('teaching:confirm', args=[self.demand.pk]), {'resource_id': self.room.pk})
        self.assertEqual(response.status_code, 302)
        self.demand.refresh_from_db()
        self.assertEqual(self.demand.status, TeachingRequest.Status.CONFIRMED)
        self.assertEqual(self.demand.assigned_resource, self.room)
        self.client.post(reverse('teaching:cancel', args=[self.demand.pk]))
        self.demand.refresh_from_db()
        self.assertEqual(self.demand.status, TeachingRequest.Status.CANCELLED)

    def test_request_form_rejects_reversed_times(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('teaching:request_create'), {
            'title': '错误时间', 'course': '算法',
            'start_at': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_at': (self.start - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'expected_attendees': 30, 'resource_kind': TeachingResource.Kind.CLASSROOM,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeachingRequest.objects.count(), 1)

    def test_teacher_can_submit_valid_request_from_form(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('teaching:request_create'), {
            'title': '上机实践', 'course': '数据库系统',
            'start_at': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_at': (self.start + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
            'expected_attendees': 25,
            'resource_kind': TeachingResource.Kind.LAB,
            'required_features': '投影', 'notes': '课程上机练习',
        })
        self.assertEqual(response.status_code, 302)
        created = TeachingRequest.objects.get(course='数据库系统')
        self.assertEqual(created.requested_by, self.teacher)
        self.assertEqual(created.status, TeachingRequest.Status.PENDING)

    def test_resource_edit_cannot_invalidate_future_booking(self):
        confirm_schedule(demand_id=self.demand.pk, resource_id=self.room.pk, user=self.admin)
        self.client.force_login(self.admin)
        response = self.client.post(reverse('teaching:resource_edit', args=[self.room.pk]), {
            'name': self.room.name,
            'code': self.room.code,
            'kind': self.room.kind,
            'location': self.room.location,
            'capacity': 10,
            'features': self.room.features,
            'description': '',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.capacity, 35)

