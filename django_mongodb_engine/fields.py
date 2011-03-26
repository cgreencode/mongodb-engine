from django.db import connections, models

from pymongo.objectid import ObjectId
from gridfs import GridFS

from djangotoolbox.fields import EmbeddedModelField as _EmbeddedModelField

__all__ = ['LegacyEmbeddedModelField', 'GridFSField', 'GridFSString']

class LegacyEmbeddedModelField(_EmbeddedModelField):
    """
    Wrapper around djangotoolbox' :class:`EmbeddedModelField` that keeps
    backwards compatibility with data generated by django-mongodb-engine < 0.3.
    """
    def to_python(self, values):
        if isinstance(values, dict):
            # In version 0.2, the layout of the serialized model instance changed.
            # Cleanup up old instances from keys that aren't used any more.
            values.pop('_app', None)
            if '_module' not in values:
                values.pop('_model', None)
            # Up to version 0.2, '_id's were added automatically.
            # Keep backwards compatibility to old data records.
            if '_id' in values:
                values['id'] = values.pop('_id')
        return super(LegacyEmbeddedModelField, self).to_python(values)

class GridFSField(models.Field):
    def __init__(self, *args, **kwargs):
        self._versioning = kwargs.pop('versioning', False)
        kwargs['max_length'] = 24
        kwargs.setdefault('default', None)
        kwargs.setdefault('null', True)
        super(GridFSField, self).__init__(*args, **kwargs)

    def db_type(self, connection):
        return 'gridfs'

    def contribute_to_class(self, model, name):
        super(GridFSField, self).contribute_to_class(model, name)
        setattr(model, self.attname, property(self._property_get, self._property_set))
        models.signals.pre_delete.connect(self._on_pre_delete, sender=model)

    def _property_get(self, model_instance):
        meta = self._get_meta(model_instance)
        id, file, _ = meta
        if file is None and id is not None:
            gridfs = self._get_gridfs(model_instance)
            file = gridfs.get(id)
            meta[FILE] = file = gridfs.get(id)
        return file

    def _property_set(self, model_instance, value):
        meta = self._get_meta(model_instance)
        if isinstance(value, ObjectId) and meta[ID] is None:
            meta[ID] = value
        else:
            meta[SHOULD_SAVE] = meta[FILE] != value
            meta[FILE] = value

    def pre_save(self, model_instance, add):
        id, file, should_save = self._get_meta(model_instance)
        if should_save:
            gridfs = self._get_gridfs(model_instance)
            if not self._versioning and id is not None:
                gridfs.delete(id)
            return gridfs.put(file)
        return id

    def _on_pre_delete(self, sender, instance, using, signal):
        self._get_gridfs(instance).delete(self._get_meta(instance)[ID])

    def _get_meta(self, model_instance):
        meta_name = '_%s_meta' % self.attname
        meta = getattr(model_instance, meta_name, None)
        if meta is None:
            meta = [None, None, None]
            setattr(model_instance, meta_name, meta)
        return meta

    def _get_gridfs(self, model_instance):
        return GridFS(connections[model_instance.__class__.objects.db].database)

class GridFSString(GridFSField):
    def _property_get(self, model):
        file = super(GridFSString, self)._property_get(model)
        if hasattr(file, 'read'):
            return file.read()
        return file

ID, FILE, SHOULD_SAVE = range(3)
