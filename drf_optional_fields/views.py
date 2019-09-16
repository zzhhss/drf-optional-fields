from django.utils.functional import cached_property

from drf_optional_fields.serializers import ReturnField


class OptionalFieldViewMixin:

    @cached_property
    def fields(self):
        return self.get_fields()

    def get_queryset(self):
        qs = super().get_queryset()
        serializer_class = self.get_serializer_class()
        if hasattr(serializer_class, 'modify_queryset'):
            qs = serializer_class.modify_queryset(qs, self.fields)
        return qs

    def get_fields(self):
        return ReturnField.many_init_from_string(self.request.query_params.get('fields'))

    def modify_context_with_fields(self, context):
        context.update(fields=self.fields)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        self.modify_context_with_fields(context)
        return context
