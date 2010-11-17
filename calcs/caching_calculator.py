import gettext
import __builtin__
from types import FunctionType

__builtin__._ = gettext.gettext

class InvalidCalculatorSpecification(Exception):
    # raised when a sub-class of CachingCalculator (or other class using
    # CachingCalculatorMeta as its meta-class) cannot be constructed, or when
    # it runs into a terminal error during calculation caused by the calculator
    # definition.
    def __init__(self, error_msg):
        self.error_msg = error_msg

    def __str__(self):
        return str(self.error_msg)

class CachingCalculatorMeta(type):
    """ Meta-class for caching calculators.
    
    When a class is created with this meta-class (i.e. when CachingCalculator
    is subclassed), two things happen (publically):

     * A read-write parameter property is created for each name listed in the
       special class attribute '__parameters__'.

     * A read-only calculated property is created corresponding to each method
       starting with the prefix 'calculate_'.

    The parameter properties are those which are not calculated but which you
    wish to have trigger recalculation of any potentially dependent calculated
    properties.

    The calculated properties perform the calculations in the corresponding
    'calculate_X' method on demand and cache the results. The dependencies of
    the calculation are automatically discovered and if any of the properties
    upon which the calculation are dependent change, the cache will be
    invalidated to allow recalculation (on demand).

    Primary drawback/gotcha: only explicit parameter properties or calculated
    properties on the same object are included in the dependency graph. If you
    have a calculation that depends on a 'foreign' parameter/calculation, you
    will need to set up a 'native' parameter to represent it and manage the
    connection out-of-band.
    """

    class CalculationCache(object):
        """ Contains the cache, dependency graph, and current call stack.
        
        The cache is a simple dictionary of keys to cached values. get(...) and
        store(...) allow access to the cache; has_valid(...) tests if a key has
        been set and has not been invalidated since. Storing a value for a key
        will invalidate any keys dependent on that key (recursively).

        The dependency graph links keys to dependent keys, so that if the
        former is changed, the latter can be automatically invalidated for
        eventual recomputation. Dependencies can be added to this graph as they
        are discovered with add_dependency(...).

        The call stack holds a list of calculations currently being performed.
        This serves two purposes: the top of the stack can tell us the current
        caller, so that we can discover the dependency graph by usage, and the
        full stack lets us detect recursive dependencies. caller(...),
        push_caller(...), and pop_caller(...) gives convenient access to the
        head of the stack, and call_stack(...) allows full access.
        """

        def __init__(self):
            self._values = dict()
            self._dependency_graph = dict()
            self._call_stack = list()

        def get(self, key):
            """ Lookup the cached value for key, if any. """
            if self.has_valid(key):
                return self._values[key]
            else:
                return None

        def store(self, key, value):
            """ Store value in the cache under key, invalidating any dependent keys. """
            self._invalidate(key)
            self._values[key] = value

        def has_valid(self, key):
            """ Query whether there is a cached value for key. """
            return key in self._values

        def _invalidate(self, key):
            # invalidate by removing the key
            if key in self._values:
                del self._values[key]
            # recursively invalidate any dependent keys
            if key in self._dependency_graph:
                for other in self._dependency_graph[key]:
                    self._invalidate(other)

        def add_dependency(self, key1, key2):
            """ Record key1 as dependent on key2. """
            if key2 not in self._dependency_graph:
                self._dependency_graph[key2] = list()
            if key1 not in self._dependency_graph[key2]:
                self._dependency_graph[key2].append(key1)

        def caller(self):
            """ Return the top element of the call stack. """
            if len(self._call_stack) == 0:
                return None
            else:
                return self._call_stack[-1]

        def push_caller(self, caller):
            """ Add an element to the top of the call stack. """
            self._call_stack.append(caller)

        def pop_caller(self):
            """ Remove the top element of the call stack. """
            if len(self._call_stack) > 0:
                self._call_stack = self._call_stack[:-1]

        def call_stack(self):
            """ Return the full call stack. """
            return self._call_stack

    class CacheProperty(object):
        """ An auto-instantiating CalculationCache object. """
        def __get__(self, obj, objtype):
            try:
                return obj._cache_object
            except AttributeError:
                obj._cache_object = CachingCalculatorMeta.CalculationCache()
                return obj._cache_object

    class ParameterProperty(object):
        """ A non-calculated value upon which calculated values might depend. """
        def __init__(self, name):
            self.name = name

        def __get__(self, obj, objtype):
            # if this property was accessed during the caller's calculation,
            # the caller must be dependent on this property
            cache = obj._cache
            caller = cache.caller()
            if caller != None:
                cache.add_dependency(caller, self.name)

            # populate the cache with a default value if this hasn't been set
            # yet (it'll probably cause an error later, but we'll give other
            # code the chance to handle it)
            if not cache.has_valid(self.name):
                cache.store(self.name, None)
            return cache.get(self.name)

        def __set__(self, obj, value):
            # although not calculated, these properties are also stored in the
            # cache to facilitate invalidation
            cache = obj._cache
            cache.store(self.name, value)

    class CalculatedProperty(object):
        """ A calculated value (upon which other calculated values might depend). """
        def __init__(self, name, calculator):
            self.name = name
            self.calculator = calculator

        def __get__(self, obj, objtype):
            # if this property was accessed during the caller's calculation,
            # the caller must be dependent on this property
            cache = obj._cache
            caller = cache.caller()
            if caller != None:
                cache.add_dependency(caller, self.name)

            # just return the cached value if we have a valid one
            if cache.has_valid(self.name):
                return cache.get(self.name)

            # no cached value, calculate it. but first make sure we're not
            # already in the middle of trying to calculate it
            if self.name in cache.call_stack():
                call_stack = cache.call_stack()
                call_stack.append(self.name)
                raise InvalidCalculatorSpecification(
                    _("recursive dependency detected: {call_stack}").
                    format(call_stack=call_stack))

            # add ourselves to the call stack while we calculate it
            cache.push_caller(self.name)
            value = self.calculator(obj)
            cache.pop_caller()

            # store the calculated value and return it
            cache.store(self.name, value)
            return value

    def __new__(meta, classname, bases, class_dict):
        # set up the auto-constructing calculation cache with a consistent name
        if '_cache' in class_dict:
            raise InvalidCalculatorSpecification(
                _("{key} already exists in the class dictionary.").
                format(key='_cache'))
        class_dict['_cache'] = meta.CacheProperty()

        # create descriptors for the parameters which need to show up in the
        # dependency graph
        parameters = class_dict.get('__parameters__', list())
        for name in parameters:
            # avoid name conflicts
            if name in class_dict:
                raise InvalidCalculatorSpecification(
                    _("{key} is listed in {parameters_key}, but that key " +
                      "already exists in the class dictionary.").
                    format(key=name, parameters_key='__parameters__'))
            class_dict[name] = meta.ParameterProperty(name)

        # create properties for the various calculations
        for name, value in class_dict.items():
            if type(value) == FunctionType and name.startswith('calculate_'):
                new_name = name[len('calculate_'):]
                # avoid name conflicts
                if new_name in class_dict:
                    raise InvalidCalculatorSpecification(
                        _("{method} calculation method is in the class " +
                          "dictionary, but the {key} key already exists in " +
                          "the class dictionary or was added via " +
                          "{parameters_key}.").
                        format(method=name, key=new_name,
                            parameters_key='__parameters__'))
                class_dict[new_name] = meta.CalculatedProperty(new_name, value)

        return type.__new__(meta, classname, bases, class_dict)

class CachingCalculator(object):
    """ Base class that incorporates the CachingCalculatorMeta class. """
    __metaclass__ = CachingCalculatorMeta
