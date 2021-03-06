import json
import time

from django.conf.urls import url
from django.contrib.auth import get_user_model
from django.core.urlresolvers import reverse
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.db.models import Q
from django.utils import formats
from django.db.models import Count

from avatar.templatetags.avatar_tags import avatar_url
from guardian.shortcuts import get_objects_for_user

from geonode.base.models import ResourceBase
from geonode.base.models import TopicCategory
from geonode.base.models import Region
from geonode.layers.models import Layer
from geonode.maps.models import Map
from geonode.datarequests.models import DataRequestProfile, ProfileRequest, DataRequest
from geonode.documents.models import Document
from geonode.groups.models import GroupProfile

from taggit.models import Tag
from django.core.serializers.json import DjangoJSONEncoder
from tastypie.serializers import Serializer
from tastypie import fields
from tastypie.authentication import SessionAuthentication
from tastypie.resources import ModelResource
from tastypie.constants import ALL
from tastypie.utils import trailing_slash

from .authorization import GeoNodeAuthorization, DataRequestAuthorization, ProfileRequestAuthorization

from pprint import pprint

FILTER_TYPES = {
    'layer': Layer,
    'map': Map,
    'document': Document,
    'old_request': DataRequestProfile,
    'profile_request': ProfileRequest,
    'data_request': DataRequest,
}


class CountJSONSerializer(Serializer):
    """Custom serializer to post process the api and add counts"""

    def get_resources_counts(self, options):
        if settings.SKIP_PERMS_FILTER:
            resources = ResourceBase.objects.all()
        else:
            resources = get_objects_for_user(
                options['user'],
                'base.view_resourcebase'
            )
        if settings.RESOURCE_PUBLISHING:
            resources = resources.filter(is_published=True)

        if options['title_filter']:
            resources = resources.filter(title__icontains=options['title_filter'])

        if options['type_filter']:
            resources = resources.instance_of(options['type_filter'])

        counts = list(resources.values(options['count_type']).annotate(count=Count(options['count_type'])))

        return dict([(c[options['count_type']], c['count']) for c in counts])

    def to_json(self, data, options=None):
        options = options or {}
        data = self.to_simple(data, options)
        counts = self.get_resources_counts(options)
        if 'objects' in data:
            for item in data['objects']:
                item['count'] = counts.get(item['id'], 0)
        # Add in the current time.
        data['requested_time'] = time.time()

        return json.dumps(data, cls=DjangoJSONEncoder, sort_keys=True)


class TypeFilteredResource(ModelResource):
    """ Common resource used to apply faceting to categories, keywords, and
    regions based on the type passed as query parameter in the form
    type:layer/map/document"""

    count = fields.IntegerField()

    def build_filters(self, filters={}):
        self.type_filter = None
        self.title_filter = None

        orm_filters = super(TypeFilteredResource, self).build_filters(filters)

        if 'type' in filters and filters['type'] in FILTER_TYPES.keys():
            self.type_filter = FILTER_TYPES[filters['type']]
        else:
            self.type_filter = None
        if 'title__icontains' in filters:
            self.title_filter = filters['title__icontains']

        return orm_filters

    def serialize(self, request, data, format, options={}):
        options['title_filter'] = getattr(self, 'title_filter', None)
        options['type_filter'] = getattr(self, 'type_filter', None)
        options['user'] = request.user

        return super(TypeFilteredResource, self).serialize(request, data, format, options)


class TagResource(TypeFilteredResource):
    """Tags api"""

    def serialize(self, request, data, format, options={}):
        options['count_type'] = 'keywords'

        return super(TagResource, self).serialize(request, data, format, options)

    class Meta:
        queryset = Tag.objects.all().order_by('name')
        resource_name = 'keywords'
        allowed_methods = ['get']
        filtering = {
            'slug': ALL,
        }
        serializer = CountJSONSerializer()


class RegionResource(TypeFilteredResource):
    """Regions api"""

    def serialize(self, request, data, format, options={}):
        options['count_type'] = 'regions'

        return super(RegionResource, self).serialize(request, data, format, options)

    class Meta:
        queryset = Region.objects.all().order_by('name')
        resource_name = 'regions'
        allowed_methods = ['get']
        filtering = {
            'name': ALL,
            'code': ALL,
        }
        if settings.API_INCLUDE_REGIONS_COUNT:
            serializer = CountJSONSerializer()


class TopicCategoryResource(TypeFilteredResource):
    """Category api"""

    def serialize(self, request, data, format, options={}):
        options['count_type'] = 'category'

        return super(TopicCategoryResource, self).serialize(request, data, format, options)

    class Meta:
        queryset = TopicCategory.objects.all()
        resource_name = 'categories'
        allowed_methods = ['get']
        filtering = {
            'identifier': ALL,
        }
        serializer = CountJSONSerializer()


class GroupResource(ModelResource):
    """Groups api"""

    detail_url = fields.CharField()
    member_count = fields.IntegerField()
    manager_count = fields.IntegerField()

    def dehydrate_member_count(self, bundle):
        return bundle.obj.member_queryset().count()

    def dehydrate_manager_count(self, bundle):
        return bundle.obj.get_managers().count()

    def dehydrate_detail_url(self, bundle):
        return reverse('group_detail', args=[bundle.obj.slug])

    class Meta:
        queryset = GroupProfile.objects.all()
        resource_name = 'groups'
        allowed_methods = ['get']
        filtering = {
            'name': ALL
        }
        ordering = ['title', 'last_modified']


class ProfileResource(TypeFilteredResource):
    """Profile api"""

    avatar_100 = fields.CharField(null=True)
    profile_detail_url = fields.CharField()
    email = fields.CharField(default='')
    layers_count = fields.IntegerField(default=0)
    maps_count = fields.IntegerField(default=0)
    documents_count = fields.IntegerField(default=0)
    current_user = fields.BooleanField(default=False)
    activity_stream_url = fields.CharField(null=True)

    def build_filters(self, filters={}):
        """adds filtering by group functionality"""

        orm_filters = super(ProfileResource, self).build_filters(filters)

        if 'group' in filters:
            orm_filters['group'] = filters['group']

        return orm_filters

    def apply_filters(self, request, applicable_filters):
        """filter by group if applicable by group functionality"""

        group = applicable_filters.pop('group', None)

        semi_filtered = super(
            ProfileResource,
            self).apply_filters(
            request,
            applicable_filters)

        if group is not None:
            semi_filtered = semi_filtered.filter(
                groupmember__group__slug=group)

        return semi_filtered

    def dehydrate_email(self, bundle):
        email = ''
        if bundle.request.user.is_authenticated():
            email = bundle.obj.email
        return email

    def dehydrate_layers_count(self, bundle):
        obj_with_perms = get_objects_for_user(bundle.request.user,
                                              'base.view_resourcebase').instance_of(Layer)
        return bundle.obj.resourcebase_set.filter(id__in=obj_with_perms.values('id')).distinct().count()

    def dehydrate_maps_count(self, bundle):
        obj_with_perms = get_objects_for_user(bundle.request.user,
                                              'base.view_resourcebase').instance_of(Map)
        return bundle.obj.resourcebase_set.filter(id__in=obj_with_perms.values('id')).distinct().count()

    def dehydrate_documents_count(self, bundle):
        obj_with_perms = get_objects_for_user(bundle.request.user,
                                              'base.view_resourcebase').instance_of(Document)
        return bundle.obj.resourcebase_set.filter(id__in=obj_with_perms.values('id')).distinct().count()

    def dehydrate_avatar_100(self, bundle):
        return avatar_url(bundle.obj, 240)

    def dehydrate_profile_detail_url(self, bundle):
        return bundle.obj.get_absolute_url()

    def dehydrate_current_user(self, bundle):
        return bundle.request.user.username == bundle.obj.username

    def dehydrate_activity_stream_url(self, bundle):
        return reverse(
            'actstream_actor',
            kwargs={
                'content_type_id': ContentType.objects.get_for_model(
                    bundle.obj).pk,
                'object_id': bundle.obj.pk})

    def prepend_urls(self):
        if settings.HAYSTACK_SEARCH:
            return [
                url(r"^(?P<resource_name>%s)/search%s$" % (
                    self._meta.resource_name, trailing_slash()
                ),
                    self.wrap_view('get_search'), name="api_get_search"),
            ]
        else:
            return []

    def serialize(self, request, data, format, options={}):
        options['count_type'] = 'owner'

        return super(ProfileResource, self).serialize(request, data, format, options)

    class Meta:
        queryset = get_user_model().objects.exclude(username='AnonymousUser')
        authentication = SessionAuthentication()
        resource_name = 'profiles'
        allowed_methods = ['get']
        ordering = ['username', 'date_joined']
        excludes = ['is_staff', 'password', 'is_superuser',
                    'is_active', 'last_login']

        filtering = {
            'username': ALL,
        }

        serializer = CountJSONSerializer()


class OwnersResource(TypeFilteredResource):
    """Owners api, lighter and faster version of the profiles api"""

    def serialize(self, request, data, format, options={}):
        options['count_type'] = 'owner'

        return super(OwnersResource, self).serialize(request, data, format, options)

    class Meta:
        queryset = get_user_model().objects.exclude(username='AnonymousUser')
        resource_name = 'owners'
        allowed_methods = ['get']
        ordering = ['username', 'date_joined']
        excludes = ['is_staff', 'password', 'is_superuser',
                    'is_active', 'last_login']

        filtering = {
            'username': ALL,
        }
        serializer = CountJSONSerializer()

REQUESTER_TYPES = {
    'commercial': 'commercial',
    'noncommercial': 'noncommercial',
    'academe': 'academe',
}


class ProfileRequestResource(ModelResource):
    """Profile Request api"""
    profile_request_detail_url = fields.CharField()
    org_type = fields.CharField()
    status = fields.CharField(attribute='status')
    status_label = fields.CharField()
    is_rejected = fields.BooleanField(default=False)
    rejection_reason = fields.CharField()
    date_submitted = fields.CharField()
    shapefile_thumbnail_url = fields.CharField(null=True)
    has_data_request = fields.BooleanField(default=False)
    data_request_id = fields.CharField()
    data_request_detail_url = fields.CharField()

    class Meta:
        authorization = ProfileRequestAuthorization()
        authentication = SessionAuthentication()
        queryset = ProfileRequest.objects.all().order_by('-created')
        resource_name = 'profile_requests'
        allowed_methods = ['get']
        ordering = ['-created', ]
        filtering = {'first_name': ALL,
                     'requester_type': ALL,
                     'status': ALL,
                     'organization': ALL,
                     'org_type': ALL,
                     'key_created_date': ALL,
                     }

    def dehydrate_profile_request_detail_url(self, bundle):
        return bundle.obj.get_absolute_url()

    def dehydrate_org_type(self, bundle):
        return bundle.obj.org_type

    def dehydrate_rejection_reason(self, bundle):
        return bundle.obj.rejection_reason

    def dehydrate_status(self, bundle):
        return bundle.obj.get_status_display()

    def dehydrate_is_rejected(self, bundle):
        return bundle.obj.status == 'rejected'

    def dehydrate_date_submitted(self, bundle):
        return formats.date_format(bundle.obj.created, "SHORT_DATETIME_FORMAT")

    def dehydrate_status_label(self, bundle):
        if bundle.obj.status == 'pending' or bundle.obj.status == 'unconfirmed':
            return 'default'
        elif bundle.obj.status == 'rejected':
            return 'danger'
        else:
            return 'success'

    def dehydrate_data_request_detail_url(self, bundle):
        if bundle.obj.data_request:
            return bundle.obj.data_request.get_absolute_url()
        else:
            return None

    def dehydrate_shapefile_thumbnail_url(self, bundle):
        if bundle.obj.data_request and bundle.obj.data_request.jurisdiction_shapefile:
            return bundle.obj.data_request.jurisdiction_shapefile.thumbnail_url
        else:
            return None

    def dehydrate_data_request_id(self, bundle):
        if bundle.obj.data_request:
            return bundle.obj.data_request.id
        else:
            return None

    def dehydrate_has_data_request(self, bundle):
        if bundle.obj.data_request:
            return True
        else:
            return False

    def apply_filters(self, request, applicable_filters):
        base_object_list = super(ProfileRequestResource, self).apply_filters(request, applicable_filters)
        query = request.GET.get('title__icontains', None)
        if query:
            query = query.split(' ')
            q = Q()
            for t in query:
                q = q | Q(first_name__icontains=t)
                q = q | Q(middle_name__icontains=t)
                q = q | Q(last_name__icontains=t)
                q = q | Q(organization__icontains=t)
            base_object_list = base_object_list.filter(q).distinct()

        return base_object_list

    def prepend_urls(self):
        if settings.HAYSTACK_SEARCH:
            return [
                url(r"^(?P<resource_name>%s)/search%s$" % (
                    self._meta.resource_name, trailing_slash()
                    ),
                    self.wrap_view('get_search'), name="api_get_search"),
            ]
        else:
            return []

class DataRequestResource(ModelResource):
    """Data Request api"""
    data_request_detail_url = fields.CharField()
    status = fields.CharField(attribute="status")
    status_label = fields.CharField()
    is_rejected = fields.BooleanField(default=False)
    rejection_reason = fields.CharField()
    date_submitted = fields.CharField()
    shapefile_thumbnail_url = fields.CharField(null=True)
    username = fields.CharField()
    profile_request_id = fields.CharField()
    first_name = fields.CharField()
    last_name = fields.CharField()
    middle_name = fields.CharField()
    organization = fields.CharField()
    org_type = fields.CharField()
    organization_other = fields.CharField()
    profile_request_detail_url = fields.CharField()

    class Meta:
        authorization = DataRequestAuthorization()
        authentication = SessionAuthentication()
        queryset = DataRequest.objects.all().order_by('-created')
        resource_name = 'data_requests'
        allowed_methods = ['get']
        ordering = ['date_submitted', ]
        filtering = {'first_name': ALL,
                     'requester_type': ALL,
                     'status': ALL,
                     'organization': ALL,
                     'date_submitted': ALL,
                     }

    def dehydrate_data_request_detail_url(self, bundle):
        return bundle.obj.get_absolute_url()

    def dehydrate_purpose(self, bundle):
        return bundle.obj.purpose

    def dehydrate_rejection_reason(self, bundle):
        return bundle.obj.rejection_reason

    def dehydrate_status(self, bundle):
        return bundle.obj.get_status_display()

    def dehydrate_is_rejected(self, bundle):
        return bundle.obj.status == 'rejected'

    def dehydrate_date_submitted(self, bundle):
        return formats.date_format(bundle.obj.created, "SHORT_DATETIME_FORMAT")

    def dehydrate_status_label(self, bundle):
        if bundle.obj.status == 'pending' or bundle.obj.status == 'cancelled' or bundle.obj.status == 'unconfirmed':
            return 'default'
        elif bundle.obj.status == 'rejected':
            return 'danger'
        else:
            return 'success'

    def dehydrate_shapefile_thumbnail_url(self, bundle):
        if bundle.obj.jurisdiction_shapefile:
            return bundle.obj.jurisdiction_shapefile.thumbnail_url
        else:
            return None

    def dehydrate_profile_request_id(self, bundle):
        return bundle.obj.profile_request_id

    def dehydrate_username(self, bundle):
        if bundle.obj.profile:
            return bundle.obj.profile.username
        else:
            return None

    def dehydrate_first_name(self, bundle):
        if bundle.obj.profile_request:
            return bundle.obj.profile_request.first_name
        elif bundle.obj.profile:
            return bundle.obj.profile.first_name
        else:
            return None

    def dehydrate_last_name(self, bundle):
        if bundle.obj.profile_request:
            return bundle.obj.profile_request.last_name
        elif bundle.obj.profile:
            return bundle.obj.profile.last_name
        else:
            return None

    def dehydrate_middle_name(self, bundle):
        if bundle.obj.profile_request:
            return bundle.obj.profile_request.middle_name
        elif bundle.obj.profile:
            return bundle.obj.profile.middle_name
        else:
            return None

    def dehydrate_organization(self, bundle):
        if bundle.obj.profile_request:
            return bundle.obj.profile_request.organization
        elif bundle.obj.profile:
            return bundle.obj.profile.organization
        else:
            return None

    def dehydrate_org_type(self, bundle):
        if bundle.obj.profile_request:
            return bundle.obj.profile_request.org_type
        elif bundle.obj.profile:
            return bundle.obj.profile.org_type
        else:
            return None

    def dehydrate_organization_other(self, bundle):
        if bundle.obj.profile_request:
            return bundle.obj.profile_request.organization_other
        else:
            return None

    def dehydrate_profile_request_detail_url(self, bundle):
        if bundle.obj.profile_request:
            return bundle.obj.profile_request.get_absolute_url()
        else:
            return None

    def apply_filters(self, request, applicable_filters):
         base_object_list = super(DataRequestResource, self).apply_filters(request, applicable_filters)

         query = request.GET.get('title__icontains', None)
         if query:
             query = query.split(' ')
             q = Q()
             for t in query:
                 q = q | Q(first_name__icontains=t)
                 q = q | Q(middle_name__icontains=t)
                 q = q | Q(last_name__icontains=t)
                 q = q | Q(organization__icontains=t)
                 q = q | Q(username__icontains=t)
             base_object_list = base_object_list.filter(q).distinct()

         return base_object_list

    def prepend_urls(self):
        if settings.HAYSTACK_SEARCH:
            return [
                url(r"^(?P<resource_name>%s)/search%s$" % (
                    self._meta.resource_name, trailing_slash()
                    ),
                    self.wrap_view('get_search'), name="api_get_search"),
            ]
        else:
            return []

class DataRequestProfileResource(ModelResource):
    """Data Request Profile api"""
    data_request_detail_url = fields.CharField()
    org_type = fields.CharField()
    req_type = fields.CharField()
    status = fields.CharField()
    status_label = fields.CharField()
    is_rejected = fields.BooleanField(default=False)
    rejection_reason = fields.CharField()
    date_submitted = fields.CharField()
    shapefile_thumbnail_url = fields.CharField(null=True)

    class Meta:
        authorization = DataRequestAuthorization()
        authentication = SessionAuthentication()
        queryset = DataRequestProfile.objects.all().order_by('-key_created_date')
        resource_name = 'old_requests'
        allowed_methods = ['get']
        ordering = ['key_created_date', ]
        filtering = {'first_name': ALL,
                     'requester_type': ALL,
                     'request_status': ALL,
                     'organization': ALL,
                     'request_status': ALL,
                     'key_created_date': ALL,
                     }

    def dehydrate_data_request_detail_url(self, bundle):
        return bundle.obj.get_absolute_url()

    def dehydrate_org_type(self, bundle):
        return bundle.obj.org_type

    def dehydrate_rejection_reason(self, bundle):
        return bundle.obj.rejection_reason

    def dehydrate_status(self, bundle):
        return bundle.obj.get_request_status_display()

    def dehydrate_is_rejected(self, bundle):
        return bundle.obj.request_status == 'rejected'

    def dehydrate_date_submitted(self, bundle):
        return formats.date_format(bundle.obj.key_created_date, "SHORT_DATETIME_FORMAT")

    def dehydrate_status_label(self, bundle):
        if bundle.obj.request_status == 'pending' or bundle.obj.request_status == 'cancelled' or bundle.obj.request_status == 'unconfirmed':
            return 'default'
        elif bundle.obj.request_status == 'rejected':
            return 'danger'
        else:
            return 'success'

    def dehydrate_shapefile_thumbnail_url(self, bundle):
        if bundle.obj.jurisdiction_shapefile:
            return bundle.obj.jurisdiction_shapefile.thumbnail_url
        else:
            return None

    def apply_filters(self, request, applicable_filters):
        base_object_list = super(DataRequestProfileResource, self).apply_filters(request, applicable_filters)

        query = request.GET.get('title__icontains', None)
        if query:
            query = query.split(' ')
            q = Q()
            for t in query:
                q = q | Q(first_name__icontains=t)
                q = q | Q(middle_name__icontains=t)
                q = q | Q(last_name__icontains=t)
                q = q | Q(organization__icontains=t)
            base_object_list = base_object_list.filter(q).distinct()

        return base_object_list

    def prepend_urls(self):
        if settings.HAYSTACK_SEARCH:
            return [
                url(r"^(?P<resource_name>%s)/search%s$" % (
                    self._meta.resource_name, trailing_slash()
                    ),
                    self.wrap_view('get_search'), name="api_get_search"),
            ]
        else:
            return []
