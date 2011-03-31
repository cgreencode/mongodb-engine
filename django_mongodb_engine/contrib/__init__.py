from django.db import models, connections
from django.db.models.query import QuerySet
from django.db.models.sql import AND
from django.db.models.sql.query import Query as SQLQuery
from .mapreduce import MapReduceMixin

def _compiler_for_queryset(qs, which='SQLCompiler'):
    connection = connections[qs.db]
    Compiler = connection.ops.compiler(which)
    return Compiler(qs.query, connection, connection.alias)

class RawQuery(SQLQuery):
    def __init__(self, model, raw_query):
        super(RawQuery, self).__init__(model)
        self.raw_query = raw_query

    def clone(self, *args, **kwargs):
        clone = super(RawQuery, self).clone(*args, **kwargs)
        clone.raw_query = self.raw_query
        return clone

class RawQueryMixin:
    def get_raw_query_set(self, raw_query):
        return QuerySet(self.model, RawQuery(self.model, raw_query), self._db)

    def raw_query(self, query=None):
        """
        Does a raw MongoDB query. The optional parameter `query` is the spec
        passed to PyMongo's :meth:`~pymongo.Collection.find` method.
        """
        return self.get_raw_query_set(query or {})

    def raw_update(self, spec_or_q, update_dict, **kwargs):
        """
        Does a raw MongoDB update. `spec_or_q` is either a MongoDB filter
        dict or a :class:`~django.db.models.query_utils.Q` instance that selects
        the records to update. `update_dict` is a MongoDB style update document
        containing either a new document or atomic modifiers such as ``$inc``.

        Keyword arguments will be passed to :meth:`pymongo.Collection.update`.
        """
        if isinstance(spec_or_q, dict):
            queryset = self.get_raw_query_set(spec_or_q)
        else:
            queryset = self.filter(spec_or_q)
        queryset._for_write = True
        compiler = _compiler_for_queryset(queryset, 'SQLUpdateCompiler')
        compiler.execute_raw(update_dict, **kwargs)

    raw_update.alters_data = True


class MapReduceResult(object):
    """
    Represents one item of a MapReduce result array.

    :param model: the model on that query the MapReduce was performed
    :param key: the *key* from the result item
    :param value: the *value* from the result item
    """
    def __init__(self, model, key, value):
        self.model = model
        self.key = key
        self.value = value

    def get_object(self):
        """
        Fetches the model instance with ``self.key`` as primary key from the
        database (doing a database query).
        """
        return self.model.objects.get(**{self.model._meta.pk.column : self.key})

    def __repr__(self):
        return '<%s model=%r key=%r value=%r>' % \
                (self.__class__.__name__, self.model.__name__, self.key, self.value)

class MongoDBQuerySet(QuerySet):
    def map_reduce(self, *args, **kwargs):
        """
        Performs a Map/Reduce on the server.

        Returns a list of :class:`.MapReduceResult` instances, one instance for
        each item in the array the MapReduce query returns.

        TODO docs

        .. versionchanged:: 0.4 TODO
        """
        # TODO: Field name substitution (e.g. id -> _id)
        drop_collection = kwargs.pop('drop_collection', False)
        compiler = _compiler_for_queryset(self)
        query = compiler.build_query()
        kwargs.setdefault('query', query._mongo_query)
        result_collection = query.collection.map_reduce(*args, **kwargs)
        try:
            for entity in result_collection.find():
                yield MapReduceResult(self.model, entity['_id'], entity['value'])
        finally:
            if drop_collection:
                result_collection.drop()


class MongoDBManager(models.Manager, RawQueryMixin):
    """
    TODO docs
    """
    def map_reduce(self, *args, **kwargs):
        return self.get_query_set().map_reduce(*args, **kwargs)

    def get_query_set(self):
        return MongoDBQuerySet(self.model, using=self._db)
