import inspect
import re
from collections import OrderedDict
from functools import partial
from typing import List, Generator

from django.db import models
from django.db.models import Prefetch
from django_queryset_exts.query import SelectAPIRelated
from rest_framework import serializers
from rest_framework.fields import SkipField
from rest_framework.relations import PKOnlyObject
from rest_framework.serializers import LIST_SERIALIZER_KWARGS


class ReturnField:
    FIELDS_REGEX = re.compile(r'{(.*)}')

    def __init__(self, name, fields=None, limit=None, **paging):
        self.name = name
        self.fields = fields or None
        self.limit = limit
        self.paging = paging

    def __repr__(self):
        return '{}{}'.format(self.name, self.fields or '')

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.name == other.name and self.fields == other.fields
        elif isinstance(other, str):
            return self.name == other
        return False

    def __hash__(self):
        return hash(self.name)

    @classmethod
    def many_init_from_fields(cls, fields_strs) -> List['ReturnField']:
        return [cls(name=field) for field in fields_strs]

    @classmethod
    def many_init_from_string(cls, fields_string) -> List['ReturnField']:
        if not fields_string:
            return []
        fields = []
        field_strings = cls.split_fields_string(fields_string)
        for field_string in field_strings:
            fields.append(cls.init_from_string(field_string))
        return fields

    @classmethod
    def init_from_string(cls, field_string) -> 'ReturnField':
        findall_result = cls.FIELDS_REGEX.findall(field_string) if field_string else None
        sub_fields_string = ''
        if findall_result:
            sub_fields_string = findall_result[0]
        sub_fields = None
        if sub_fields_string:
            sub_fields = cls.many_init_from_string(sub_fields_string)
        return cls(field_string.split('{')[0], sub_fields)

    @staticmethod
    def split_fields_string(s):
        strings = []
        this_string = ''
        left_count = 0
        for c in s:
            if c == ',' and not left_count:
                strings.append(this_string)
                this_string = ''
                continue
            this_string += c
            if c == '{':
                left_count += 1
            elif c == '}':
                left_count -= 1

        if this_string:
            strings.append(this_string)
        return strings

    @classmethod
    def handle_fields_by_fields(cls, rest_fields, return_fields) -> Generator:
        for field_name, field in rest_fields.items():
            if return_fields and field_name not in return_fields:
                continue
            if not field.write_only:
                yield field

    @classmethod
    def handle_result_by_fields(cls, result, return_fields: List['ReturnField']):
        if not return_fields:
            return result
        fields_map = dict((field.name, field) for field in return_fields)
        if isinstance(result, dict):
            for key in list(result.keys()):
                if key not in return_fields:
                    result.pop(key, None)
                    continue
                field = fields_map.get(key)
                if field.fields:
                    result[key] = cls.handle_result_by_fields(result[key], field.fields)
        elif isinstance(result, list):
            for item in result:
                cls.handle_result_by_fields(item, return_fields)
        return result


class OptionalFieldsMixin:
    def __init__(self, *args, **kwargs):
        super(OptionalFieldsMixin, self).__init__(*args, **kwargs)
        fields = self.context.pop('fields', None)
        self.allowed_fields = fields

    @classmethod
    def many_init(cls, *args, **kwargs):
        # copy from rest
        allow_empty = kwargs.pop('allow_empty', None)
        child_serializer = cls(*args, **kwargs)
        list_kwargs = {
            'child': child_serializer,
        }
        if allow_empty is not None:
            list_kwargs['allow_empty'] = allow_empty
        list_kwargs.update({
            key: value for key, value in kwargs.items()
            if key in LIST_SERIALIZER_KWARGS
        })
        meta = getattr(cls, 'Meta', None)
        list_serializer_class = getattr(meta, 'list_serializer_class', OptionalFieldsListSerializer)
        return list_serializer_class(*args, **list_kwargs)

    def get_readable_fields(self, fields: List['ReturnField']):
        return ReturnField.handle_fields_by_fields(self.fields, fields)

    def handle_result_fields(self, result, fields):
        _ = self
        return ReturnField.handle_result_by_fields(result, fields)

    def to_representation(self, instance, fields=None):
        """
        Object instance -> Dict of primitive datatypes.
        """
        fields = fields or self.allowed_fields or self.optional_fields()
        sub_allowed_fields = dict((field.name, field.fields) for field in fields) if fields else dict()
        ret = OrderedDict()
        fields = self.get_readable_fields(fields)

        for field in fields:
            try:
                attribute = field.get_attribute(instance)
            except SkipField:
                continue

            # We skip `to_representation` for `None` values so that fields do
            # not have to explicitly deal with that case.
            #
            # For related fields with `use_pk_only_optimization` we need to
            # resolve the pk value.
            check_for_none = attribute.pk if isinstance(attribute, PKOnlyObject) else attribute
            if check_for_none is None:
                ret[field.field_name] = None
            else:
                method = field.to_representation
                sub_fields = sub_allowed_fields.get(field.field_name)
                try:
                    inspect.signature(method).bind_partial(instance, fields=fields)
                    ret[field.field_name] = method(attribute, fields=sub_fields)
                except TypeError:
                    ret[field.field_name] = ReturnField.handle_result_by_fields(method(attribute), sub_fields)
        return ret

    @classmethod
    def optional_fields(cls, fields=None):
        if fields:
            return fields
        fs = getattr(cls.Meta, 'default_fields', None)
        if fs:
            return ReturnField.many_init_from_fields(fs)
        return None

    @classmethod
    def get_queries(cls, fields: List['ReturnField'], parent=None):
        fields = cls.optional_fields(fields)
        select_relateds = set()
        prefetches = set()
        api_relateds = set()
        if not fields:
            return select_relateds, prefetches, api_relateds
        fields_related_query = getattr(cls.Meta, 'fields_related_query', dict()) or dict()
        for field in fields:
            field_related_query = fields_related_query.get(field.name)
            if field_related_query:
                for index, field_related_query_ in enumerate(field_related_query):
                    full_query = cls._prefix_with_parent(parent, field_related_query_)
                    if isinstance(full_query, str):
                        select_relateds.add(full_query)
                    elif isinstance(full_query, Prefetch):
                        prefetches.add(full_query)
                    elif isinstance(full_query, SelectAPIRelated):
                        api_relateds.add(full_query)
                    if index == 0:
                        field_field = cls._declared_fields.get(field.name)
                        if field_field and hasattr(field_field, 'get_queries'):
                            s1, s2, s3 = field_field.get_queries(field.fields, full_query)
                            select_relateds.update(s1)
                            prefetches.update(s2)
                            api_relateds.update(s3)
        pass
        return list(sorted(select_relateds)), \
               list(sorted(prefetches, key=lambda x: x.prefetch_through)), \
               list(sorted(api_relateds, key=lambda x: x.select_through))

    @classmethod
    def modify_queryset(cls, queryset, field=None):
        select_relateds, prefetches, api_relateds = cls.get_queries(field, None)
        queryset = queryset.select_related(*select_relateds) \
            .prefetch_related(*prefetches)
        if hasattr(queryset, 'select_api_related'):
            queryset = queryset.select_api_related(*api_relateds)
        return queryset

    @classmethod
    def _prefix_with_parent(cls, parent, this):
        if not parent:
            return this
        if isinstance(parent, str):
            if isinstance(this, str):
                return '{}__{}'.format(parent, this)
            elif isinstance(this, Prefetch):
                return Prefetch('{}__{}'.format(parent, this.prefetch_through))
            elif isinstance(this, SelectAPIRelated):
                return SelectAPIRelated('{}__{}'.format(parent, this.select_through))
        elif isinstance(parent, Prefetch):
            query_str = parent.prefetch_through
            if isinstance(this, str):
                return Prefetch('{}__{}'.format(query_str, this))
            elif isinstance(this, Prefetch):
                return Prefetch('{}__{}'.format(query_str, this.prefetch_through))
            elif isinstance(this, SelectAPIRelated):
                return SelectAPIRelated('{}__{}'.format(query_str, this.select_through))
        return None


class OptionalFieldsListSerializer(OptionalFieldsMixin, serializers.ListSerializer):
    def to_representation(self, data, fields=None):
        iterable = data.all() if isinstance(data, models.Manager) else data
        try:
            inspect.signature(self.child.to_representation).bind(data, fields=fields)
            to_representation_method = partial(self.child.to_representation, fields=fields)
            result = [
                to_representation_method(item) for item in iterable
            ]
        except TypeError:
            to_representation_method = self.child.to_representation
            result = [
                self.handle_result_fields(to_representation_method(item), fields) for item in iterable
            ]

        return result
