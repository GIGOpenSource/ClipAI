from rest_framework.permissions import BasePermission


class IsStaffUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsOwnerOrAdmin(BasePermission):
    """Allow access if user is superuser or owns the object.

    Ownership resolution rules (any matches counts as owner):
    - obj.owner == request.user
    - getattr(obj, 'owner_id') == request.user.id
    - obj.created_by == request.user
    - getattr(obj, 'scheduled_task', None) and obj.scheduled_task.owner == request.user
    """

    def has_permission(self, request, view):
        # Only object-level checks; allow and defer to has_object_permission
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated and user.is_staff):
            return False
        if getattr(user, 'is_superuser', False):
            return True
        # Direct owner relations
        if getattr(obj, 'owner', None) is not None:
            try:
                return obj.owner_id == user.id
            except Exception:
                return obj.owner == user
        if getattr(obj, 'owner_id', None) is not None:
            return obj.owner_id == user.id
        if getattr(obj, 'created_by', None) is not None:
            return obj.created_by_id == user.id if hasattr(obj, 'created_by_id') else obj.created_by == user
        # Nested scheduled_task.owner
        st = getattr(obj, 'scheduled_task', None)
        if st is not None:
            return getattr(st, 'owner_id', None) == user.id
        return False

