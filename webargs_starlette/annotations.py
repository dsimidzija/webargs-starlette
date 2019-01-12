import typing
import inspect
from collections.abc import Mapping, Iterable, Sequence, MutableSequence

from starlette.requests import Request
from marshmallow import Schema, fields
from marshmallow.fields import Field
from webargs import core

DEFAULT_TYPE_MAPPING = Schema.TYPE_MAPPING.copy()
DEFAULT_TYPE_MAPPING.update(
    {
        dict: fields.Dict,
        list: fields.List,
        Mapping: fields.Dict,
        typing.Mapping: fields.Dict,
        typing.Dict: fields.Dict,
        Iterable: fields.List,
        typing.Iterable: fields.List,
        Sequence: fields.List,
        typing.Sequence: fields.List,
        MutableSequence: fields.List,
        typing.MutableSequence: fields.List,
        typing.List: fields.List,
        typing.AnyStr: fields.String,
    }
)


# Marshmallow type mapping
TypeMapping = typing.Mapping[typing.Type, typing.Type[Field]]


def _type2field(
    name: str,
    type_: type,
    signature: inspect.Signature,
    type_mapping: TypeMapping,
    **kwargs,
) -> Field:
    if isinstance(type_, Field):
        return type_
    else:
        origin_cls = getattr(type_, "__origin__", None) or type_
        try:
            field_cls = type_mapping[origin_cls]
        except KeyError:
            if type(type_) is typing.TypeVar:
                field_cls = fields.Field
            else:
                raise TypeError(
                    "Cannot create field from type annotation "
                    f'for "{name}". Pass a TypeMapping '
                    f"that includes {origin_cls}."
                )
        default = signature.parameters[name].default
        required = default is inspect.Parameter.empty
        field_kwargs = {"required": required}
        if not required:
            field_kwargs["missing"] = default

        # Handle container fields
        if issubclass(field_cls, fields.List):
            args = getattr(type_, "__args__", [])
            if args:
                inner_type = args[0]
                container = _type2field(name, inner_type, signature, type_mapping)
            else:
                container = fields.Field()
            field_kwargs["cls_or_instance"] = container
        elif (
            issubclass(field_cls, fields.Dict) and core.MARSHMALLOW_VERSION_INFO[0] >= 3
        ):
            args = getattr(type_, "__args__", [])
            if args:
                key_type, val_type = args
                key_container = _type2field(name, key_type, signature, type_mapping)
                field_kwargs["keys"] = key_container
                value_container = _type2field(name, val_type, signature, type_mapping)
                field_kwargs["values"] = value_container
        field_kwargs.update(kwargs)
        return field_cls(**field_kwargs)


def annotations2schema(
    func: typing.Callable, type_mapping: typing.Optional[TypeMapping] = None
) -> Schema:
    type_mapping = type_mapping or DEFAULT_TYPE_MAPPING
    annotations = getattr(func, "__annotations__", {})
    signature = inspect.signature(func)
    fields_dict = {}
    for name, annotation in annotations.items():
        # Skip over request argument and return annotation
        if name == "return" or (
            isinstance(annotation, type) and issubclass(annotation, Request)
        ):
            continue

        fields_dict[name] = _type2field(name, annotation, signature, type_mapping)
    return core.dict2schema(fields_dict)
