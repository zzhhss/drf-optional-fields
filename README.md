drf-optional-fields
=============
A django-restframework extension to dynamically specify the returned field.


Requirements
------------

* **Python**: 3.6, 3.7
* **Django**: 2.0, 2.1, 2.2
* **DRF**: 3.9

Installation
------------

Install using pip:

    pip install django-queryset-exts
    pip install drf-optional-fields

Example:
------------
Use ``fields`` in query parameters to specify the returned field.
For example, ``fields=id,name,info{city{name},location}`` will return a dict like below: 
```
{
    "id": "id",
    "name": "A",
    "info": {
        "city": {
            "name": "city name"
        },
        "location": "localtion"
    }
}
```

Obviously, it refers to [facebook field](https://developers.facebook.com/docs/graph-api/using-graph-api/#fields)

Usage
------------

First, make your serializer class inherit from ``drf_optional_fields.serializers.OptionalFieldsMixin``

```Python
from django.db.models.query import Prefetch
from rest_framework import serializers

from django_queryset_exts.query import SelectAPIRelated
from drf_optional_fields.serializers import OptionalFieldsMixin


class MyModelsOptionalFieldsSerializer(OptionalFieldsMixin, serializers.ModelSerializer):
    class Meta:
        models = MyModel
        fields = ('field1', 'field2', 'foreign_key_field', 'reverse_many_to_one_field', 'remote_uuid_field')
        
        # use those configs to reduce queries to db 
        fields_related_query = {
            'foreign_key_field': ('foreign_key_field',),  # use foreign key field name directly
            'remote_uuid_field': (SelectAPIRelated('remote_uuid_field'),),
            'reverse_many_to_one_field': (Prefetch('reverse_many_to_one_field'))
        }
        
        default_fields = deepcopy(fields)  # change this line to specify default fields, for example: default_fields = ('field1', )

```

Then, make your api view inherit from ``drf_optional_fields.views.OptionalFieldViewMixin``

```Python
from rest_framework.generics import ListAPIView
from drf_optional_fields.views import OptionalFieldViewMixin

class MyModelListView(OptionalFieldViewMixin, ListAPIView):
    queryset = MyModel.objects.filter(is_deleted=False)
    serializer_class = MyModelsOptionalFieldsSerializer

```
It's done.