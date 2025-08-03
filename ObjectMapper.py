import sqlite3
import os
from typing import Any, Dict, List, Optional, Type
from datetime import datetime
import threading

class DatabaseManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.connections = {}
            self.default_db = 'live_rocket.db'
            self.initialized = True
    
    def get_connection(self, db_name=None):
        """Get database connection for current thread"""
        thread_id = threading.get_ident()
        db_name = db_name or self.default_db
        
        if thread_id not in self.connections:
            self.connections[thread_id] = sqlite3.connect(db_name)
            self.connections[thread_id].row_factory = sqlite3.Row
        
        return self.connections[thread_id]
    
    def execute(self, query, params=None, db_name=None):
        """Execute SQL query"""
        conn = self.get_connection(db_name)
        cursor = conn.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        conn.commit()
        return cursor

class Field:
    """Base field class"""
    def __init__(self, null=True, default=None, unique=False, primary_key=False):
        self.null = null
        self.default = default
        self.unique = unique
        self.primary_key = primary_key
        self.name = None  # Set by metaclass
    
    def to_sql(self):
        """Convert field to SQL column definition"""
        sql_type = self.get_sql_type()
        constraints = []
        
        if self.primary_key:
            constraints.append("PRIMARY KEY")
        if not self.null:
            constraints.append("NOT NULL")
        if self.unique:
            constraints.append("UNIQUE")
        
        constraint_str = " " + " ".join(constraints) if constraints else ""
        return f"{self.name} {sql_type}{constraint_str}"
    
    def get_sql_type(self):
        return "TEXT"
    
    def validate(self, value):
        """Validate field value"""
        if value is None and not self.null:
            raise ValueError(f"Field {self.name} cannot be null")
        return value
    
    def to_python(self, value):
        """Convert database value to Python value"""
        return value
    
    def to_db(self, value):
        """Convert Python value to database value"""
        return value

class CharField(Field):
    def __init__(self, max_length=255, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length
    
    def get_sql_type(self):
        return f"VARCHAR({self.max_length})"
    
    def validate(self, value):
        value = super().validate(value)
        if value is not None:
            if len(str(value)) > self.max_length:
                raise ValueError(f"Value too long for {self.name} (max {self.max_length})")
        return str(value) if value is not None else None

class IntegerField(Field):
    def get_sql_type(self):
        return "INTEGER"
    
    def to_python(self, value):
        return int(value) if value is not None else None
    
    def validate(self, value):
        value = super().validate(value)
        if value is not None:
            try:
                return int(value)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid integer value for {self.name}")
        return value

class FloatField(Field):
    def get_sql_type(self):
        return "REAL"
    
    def to_python(self, value):
        return float(value) if value is not None else None

class BooleanField(Field):
    def get_sql_type(self):
        return "BOOLEAN"
    
    def to_python(self, value):
        if value is None:
            return None
        return bool(value)
    
    def to_db(self, value):
        if value is None:
            return None
        return 1 if value else 0

class DateTimeField(Field):
    def __init__(self, auto_now=False, auto_now_add=False, **kwargs):
        super().__init__(**kwargs)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add
    
    def get_sql_type(self):
        return "DATETIME"
    
    def to_python(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value
    
    def to_db(self, value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return value

class QuerySet:
    def __init__(self, model_class):
        self.model_class = model_class
        self.conditions = []
        self.order_by_fields = []
        self.limit_count = None
        self.offset_count = None
    
    def filter(self, **kwargs):
        """Add WHERE conditions"""
        new_qs = self._clone()
        for field_name, value in kwargs.items():
            new_qs.conditions.append((field_name, '=', value))
        return new_qs
    
    def exclude(self, **kwargs):
        """Add WHERE NOT conditions"""
        new_qs = self._clone()
        for field_name, value in kwargs.items():
            new_qs.conditions.append((field_name, '!=', value))
        return new_qs
    
    def order_by(self, *fields):
        """Add ORDER BY clause"""
        new_qs = self._clone()
        new_qs.order_by_fields = list(fields)
        return new_qs
    
    def limit(self, count):
        """Add LIMIT clause"""
        new_qs = self._clone()
        new_qs.limit_count = count
        return new_qs
    
    def offset(self, count):
        """Add OFFSET clause"""
        new_qs = self._clone()
        new_qs.offset_count = count
        return new_qs
    
    def all(self):
        """Execute query and return all results"""
        query, params = self._build_query()
        db = DatabaseManager()
        cursor = db.execute(query, params)
        
        results = []
        for row in cursor.fetchall():
            instance = self.model_class()
            for field_name, field in self.model_class._fields.items():
                value = row[field_name] if field_name in row.keys() else None
                setattr(instance, field_name, field.to_python(value))
            results.append(instance)
        
        return results
    
    def first(self):
        """Get first result or None"""
        results = self.limit(1).all()
        return results[0] if results else None
    
    def get(self, **kwargs):
        """Get single object matching criteria"""
        if kwargs:
            queryset = self.filter(**kwargs)
        else:
            queryset = self
        
        results = queryset.all()
        if len(results) == 0:
            raise self.model_class.DoesNotExist("Object not found")
        elif len(results) > 1:
            raise self.model_class.MultipleObjectsReturned("Multiple objects found")
        return results[0]
    
    def count(self):
        """Count matching records"""
        query = f"SELECT COUNT(*) FROM {self.model_class._table_name}"
        if self.conditions:
            where_clause, params = self._build_where()
            query += f" WHERE {where_clause}"
        else:
            params = []
        
        db = DatabaseManager()
        cursor = db.execute(query, params)
        return cursor.fetchone()[0]
    
    def delete(self):
        """Delete matching records"""
        query = f"DELETE FROM {self.model_class._table_name}"
        if self.conditions:
            where_clause, params = self._build_where()
            query += f" WHERE {where_clause}"
        else:
            params = []
        
        db = DatabaseManager()
        cursor = db.execute(query, params)
        return cursor.rowcount
    
    def _clone(self):
        """Create a copy of this queryset"""
        new_qs = QuerySet(self.model_class)
        new_qs.conditions = self.conditions.copy()
        new_qs.order_by_fields = self.order_by_fields.copy()
        new_qs.limit_count = self.limit_count
        new_qs.offset_count = self.offset_count
        return new_qs
    
    def _build_query(self):
        """Build complete SQL query"""
        query = f"SELECT * FROM {self.model_class._table_name}"
        params = []
        
        if self.conditions:
            where_clause, where_params = self._build_where()
            query += f" WHERE {where_clause}"
            params.extend(where_params)
        
        if self.order_by_fields:
            order_fields = []
            for field in self.order_by_fields:
                if field.startswith('-'):
                    order_fields.append(f"{field[1:]} DESC")
                else:
                    order_fields.append(f"{field} ASC")
            query += f" ORDER BY {', '.join(order_fields)}"
        
        if self.limit_count:
            query += f" LIMIT {self.limit_count}"
        
        if self.offset_count:
            query += f" OFFSET {self.offset_count}"
        
        return query, params
    
    def _build_where(self):
        """Build WHERE clause"""
        conditions = []
        params = []
        
        for field_name, operator, value in self.conditions:
            conditions.append(f"{field_name} {operator} ?")
            params.append(value)
        
        return " AND ".join(conditions), params

# Model metaclass to handle field discovery
class ModelMeta(type):
    def __new__(cls, name, bases, attrs):
        # Don't process the base Model class
        if name == 'Model':
            return super().__new__(cls, name, bases, attrs)

        fields = {}
        for key, value in list(attrs.items()):
            if isinstance(value, Field):
                value.name = key
                fields[key] = value
                attrs.pop(key)

        attrs['_fields'] = fields
        attrs['_table_name'] = attrs.get('_table_name', name.lower())

        new_class = super().__new__(cls, name, bases, attrs)
        
        # Add field properties
        for field_name, field in fields.items():
            cls._create_field_property(new_class, field_name, field)
        
        return new_class
    
    @staticmethod
    def _create_field_property(cls, field_name, field):
        """Create property for field access"""
        private_name = f'_{field_name}'
        
        def getter(self):
            return getattr(self, private_name, field.default)
        
        def setter(self, value):
            validated_value = field.validate(value)
            setattr(self, private_name, validated_value)
        
        setattr(cls, field_name, property(getter, setter))

class Model(metaclass=ModelMeta):
    class DoesNotExist(Exception):
        pass
    
    class MultipleObjectsReturned(Exception):
        pass
    
    def __init__(self, **kwargs):
        # Set field values from kwargs
        for field_name, value in kwargs.items():
            if field_name in self._fields:
                setattr(self, field_name, value)
        
        # Set default values for fields not provided
        for field_name, field in self._fields.items():
            if not hasattr(self, f'_{field_name}') and field.default is not None:
                setattr(self, field_name, field.default)
    
    @classmethod
    def create_table(cls):
        """Create database table for this model"""
        fields_sql = []
        for field_name, field in cls._fields.items():
            fields_sql.append(field.to_sql())
        
        query = f"""
        CREATE TABLE IF NOT EXISTS {cls._table_name} (
            {', '.join(fields_sql)}
        )
        """
        
        db = DatabaseManager()
        db.execute(query)
        print(f"✅ Table '{cls._table_name}' created successfully")
    
    @classmethod
    def objects(cls):
        """Return QuerySet for this model"""
        return QuerySet(cls)
    
    @classmethod
    def all(cls):
        """Get all objects"""
        return cls.objects().all()
    
    @classmethod
    def filter(cls, **kwargs):
        """Filter objects"""
        return cls.objects().filter(**kwargs)
    
    @classmethod
    def get(cls, **kwargs):
        """Get single object"""
        return cls.objects().get(**kwargs)
    
    @classmethod
    def create(cls, **kwargs):
        """Create and save new object"""
        instance = cls(**kwargs)
        instance.save()
        return instance
    
    def save(self):
        """Save object to database"""
        # Handle auto_now and auto_now_add fields
        for field_name, field in self._fields.items():
            if isinstance(field, DateTimeField):
                if field.auto_now_add and not hasattr(self, f'_{field_name}'):
                    setattr(self, field_name, datetime.now())
                elif field.auto_now:
                    setattr(self, field_name, datetime.now())
        
        # Check if this is an insert or update
        pk_field = self._get_primary_key_field()
        if pk_field and hasattr(self, f'_{pk_field.name}') and getattr(self, pk_field.name) is not None:
            self._update()
        else:
            self._insert()
    
    def delete(self):
        """Delete this object from database"""
        pk_field = self._get_primary_key_field()
        if not pk_field or not hasattr(self, f'_{pk_field.name}'):
            raise ValueError("Cannot delete object without primary key")
        
        pk_value = getattr(self, pk_field.name)
        query = f"DELETE FROM {self._table_name} WHERE {pk_field.name} = ?"
        
        db = DatabaseManager()
        cursor = db.execute(query, [pk_value])
        return cursor.rowcount > 0
    
    def _insert(self):
        """Insert new record"""
        field_names = []
        values = []
        placeholders = []
        
        for field_name, field in self._fields.items():
            if hasattr(self, f'_{field_name}'):
                field_names.append(field_name)
                value = getattr(self, field_name)
                values.append(field.to_db(value))
                placeholders.append('?')
        
        if not field_names:
            raise ValueError("No fields to insert")
        
        query = f"""
        INSERT INTO {self._table_name} ({', '.join(field_names)})
        VALUES ({', '.join(placeholders)})
        """
        
        db = DatabaseManager()
        cursor = db.execute(query, values)
        
        # Set primary key if it was auto-generated
        pk_field = self._get_primary_key_field()
        if pk_field and pk_field.primary_key and not hasattr(self, f'_{pk_field.name}'):
            setattr(self, pk_field.name, cursor.lastrowid)
    
    def _update(self):
        """Update existing record"""
        pk_field = self._get_primary_key_field()
        pk_value = getattr(self, pk_field.name)
        
        field_names = []
        values = []
        
        for field_name, field in self._fields.items():
            if field_name != pk_field.name and hasattr(self, f'_{field_name}'):
                field_names.append(f"{field_name} = ?")
                value = getattr(self, field_name)
                values.append(field.to_db(value))
        
        if not field_names:
            return  # Nothing to update
        
        values.append(pk_value)
        query = f"""
        UPDATE {self._table_name}
        SET {', '.join(field_names)}
        WHERE {pk_field.name} = ?
        """
        
        db = DatabaseManager()
        db.execute(query, values)
    
    def _get_primary_key_field(self):
        """Get the primary key field"""
        for field_name, field in self._fields.items():
            if field.primary_key:
                return field
        return None
    
    def __str__(self):
        pk_field = self._get_primary_key_field()
        if pk_field and hasattr(self, f'_{pk_field.name}'):
            pk_value = getattr(self, pk_field.name)
            return f"{self.__class__.__name__}(id={pk_value})"
        return f"{self.__class__.__name__}(unsaved)"
    
    def __repr__(self):
        return self.__str__()

