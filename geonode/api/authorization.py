from tastypie.authorization import DjangoAuthorization
from tastypie.exceptions import Unauthorized

from guardian.shortcuts import get_objects_for_user


class GeoNodeAuthorization(DjangoAuthorization):

    """Object level API authorization based on GeoNode granular
    permission system"""

    def read_list(self, object_list, bundle):
        permitted_ids = get_objects_for_user(
            bundle.request.user,
            'base.view_resourcebase').values('id')

        return object_list.filter(id__in=permitted_ids)

    def read_detail(self, object_list, bundle):
        return bundle.request.user.has_perm(
            'view_resourcebase',
            bundle.obj.get_self_resource())

    def create_list(self, object_list, bundle):
        # TODO implement if needed
        raise Unauthorized()

    def create_detail(self, object_list, bundle):
        return bundle.request.user.has_perm(
            'add_resourcebase',
            bundle.obj.get_self_resource())

    def update_list(self, object_list, bundle):
        # TODO implement if needed
        raise Unauthorized()

    def update_detail(self, object_list, bundle):
        return bundle.request.user.has_perm(
            'change_resourcebase',
            bundle.obj.get_self_resource())

    def delete_list(self, object_list, bundle):
        # TODO implement if needed
        raise Unauthorized()

    def delete_detail(self, object_list, bundle):
        return bundle.request.user.has_perm(
            'delete_resourcebase',
            bundle.obj.get_self_resource())

class DataRequestAuthorization(DjangoAuthorization):

    def read_list(self, object_list, bundle):
        if bundle.request.user.is_superuser:
            return object_list
        else:
            return object_list.filter(profile=bundle.request.user)

    def read_detail(self, object_list, bundle):
        if bundle.request.user.is_superuser:
            return object_list
        else:
            return object_list.filter(profile=bundle.request.user)

    def create_list(self, object_list, bundle):
        # TODO implement if needed
        raise Unauthorized()

    def create_detail(self, object_list, bundle):
        raise Unauthorized()

    def update_list(self, object_list, bundle):
        # TODO implement if needed
        raise Unauthorized()

    def update_detail(self, object_list, bundle):
        raise Unauthorized()

    def delete_list(self, object_list, bundle):
        # TODO implement if needed
        raise Unauthorized()

    def delete_detail(self, object_list, bundle):
        raise Unauthorized()

class ProfileRequestAuthorization(DjangoAuthorization):

    def read_list(self, object_list, bundle):
        if bundle.request.user.is_superuser:
            return object_list
        else:
            raise Unauthorized()

    def read_detail(self, object_list, bundle):
        if bundle.request.user.is_superuser:
            return object_list
        else:
            return Unauthorized()

    def create_list(self, object_list, bundle):
        # TODO implement if needed
        raise Unauthorized()

    def create_detail(self, object_list, bundle):
        raise Unauthorized()

    def update_list(self, object_list, bundle):
        # TODO implement if needed
        raise Unauthorized()

    def update_detail(self, object_list, bundle):
        raise Unauthorized()

    def delete_list(self, object_list, bundle):
        # TODO implement if needed
        raise Unauthorized()

    def delete_detail(self, object_list, bundle):
        raise Unauthorized()
