""" Defines JSON-format encoding and decoding functions """
from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************

import sys as _sys
import importlib as _importlib
import json as _json
import base64 as _base64
import numpy as _np
import uuid as _uuid
import collections as _collections
import pygsti.objects

if _sys.version_info >= (3, 0):
    range_type = range
else:
    range_type = xrange

def class_hasattr(instance, attr):
    """Helper function for checking if `instance.__class__` has an attribute"""
    return hasattr(instance.__class__,attr)

def encode_obj(py_obj, binary):
    """ 
    Returns JSON-compatible version of `py_obj`.

    Constructs in-memory a JSON-format-compatible copy of the Python object
    `py_obj`, handling pyGSTi objects appropriately.  When `binary=False`,
    the output must contain only ASCII-compatible strings (no 'bytes'),
    otherwise the output is allowed to contain non-ASCII string values (OK for
    binary formats like MSGPACK and BSON).

    Parameters
    ----------
    py_obj : object
        The object to encode.

    binary : bool
        Whether the output is allowed to have binary-mode strings or not.

    Returns
    -------
    object
        A JSON-format compatible object.  Usually a dict, list, or string.
    """
    #print("DB: encoding type ", type(py_obj)) #DEBUG
    is_pygsti_obj = hasattr(py_obj,'__class__') and \
                    hasattr(py_obj.__class__,'__module__') and \
                    py_obj.__class__.__module__.startswith('pygsti')

    is_pygsti_class = isinstance(py_obj,type) and hasattr(py_obj,'__module__') \
                      and py_obj.__module__.startswith('pygsti')

    # Pygsti class encoding
    if is_pygsti_class: # or class_hasattr(py_obj, '__pygsti_getstate__')
        return {'__pygsticlass__': (py_obj.__module__,py_obj.__name__)}

    # Pygsti object encoding
    elif is_pygsti_obj: # or class_hasattr(py_obj, '__pygsti_getstate__')

        #Get State (and/or init args)
        if class_hasattr(py_obj, '__pygsti_reduce__'):
            red = py_obj.__pygsti_reduce__() #returns class, construtor_args, state
            assert(red[0] is py_obj.__class__), "No support for weird reducing!"
            init_args = red[1] if len(red) > 1 else []
            state = red[2] if len(red) > 2 else {}
            if state is None: state = {}
            state.update({ '__init_args__': init_args })
        elif class_hasattr(py_obj, '__pygsti_getstate__'):
            state = py_obj.__pygsti_getstate__() #must return a dict
        elif class_hasattr(py_obj,'__getstate__'):
            state = py_obj.__getstate__()
        elif hasattr(py_obj,'__dict__'):
            state = py_obj.__dict__  #take __dict__ as state
        else:
            state = None

        if state is None: #Note: __dict__ and __getstate__ may *return* None (python 2.7)
            if hasattr(py_obj,'_asdict'): #named tuples
                state = { '__init_args__': list(py_obj._asdict().values()) }
                  # values will be ordered as per __init__ so no need for keys
            else:
                raise ValueError("Can't get state of %s object" % type(py_obj))
            

        d = { k: encode_obj(v,binary) for k,v in state.items() }

        #DEBUG (instead of above line)
        #d = {}
        ##print("DB: Encoding state for %s object:" % type(py_obj))
        #for k,v in state.items():
        #    #print("Encoding key: ",k)
        #    d[k] = encode_obj(v)
        #    try: _json.dumps(d[k])
        #    except Exception as e:
        #        print("Cannot JSON %s key: " % k, d[k])
        #        raise e


        d.update({ '__pygstiobj__': (py_obj.__class__.__module__,
                                     py_obj.__class__.__name__)})

        #Currently, don't add standard-base-class state
        #if we know how to __init__, since we'll assume this
        # should initialize the entire (base class included) instance
        encode_std_base = bool('__init_args__' not in d)
        
        if encode_std_base:
            std_encode = encode_std_obj(py_obj, binary)
            if std_encode is not py_obj: #if there's something to encode
                # this pygsti object is also a standard-object instance
                assert(isinstance(std_encode,dict))
                d['__std_base__'] = std_encode

        #try:
        #    _json.dumps(d)
        #except Exception as e:
        #    print("Cannot JSON ",type(py_obj))
        #    raise e
            
        return d
    else:
        return encode_std_obj(py_obj, binary)

def encode_std_obj(py_obj, binary):
    """ 
    Helper to :func:`encode_obj` that encodes only "standard" (non-pyGSTi) types
    """
    # Other builtin or standard object encoding
    if isinstance(py_obj, tuple):
        return {'__tuple__': [encode_obj(v,binary) for v in py_obj]}
    elif isinstance(py_obj, list):
        return {'__list__': [encode_obj(v,binary) for v in py_obj]}
    elif isinstance(py_obj, set):
        return {'__set__': [encode_obj(v,binary) for v in py_obj]}
    elif isinstance(py_obj, slice):
        return {'__slice__': [encode_obj(py_obj.start,binary),
                              encode_obj(py_obj.stop,binary),
                              encode_obj(py_obj.step,binary)] }
    elif isinstance(py_obj, range_type):
        if _sys.version_info >= (3, 0):
            return {'__range__': (py_obj.start, py_obj.stop, py_obj.step) }
        else:
            return {'__list__': list(py_obj) } #python2 -> serialze ranges as lists
    elif isinstance(py_obj, _collections.OrderedDict):
        return {'__odict__': [(encode_obj(k,binary),encode_obj(v,binary))
                              for k,v in py_obj.items()]}
    elif isinstance(py_obj, _collections.Counter):
        return {'__counter__': [(encode_obj(k,binary),encode_obj(v,binary))
                              for k,v in dict(py_obj).items()]}
    elif isinstance(py_obj, dict):
        return {'__ndict__': [(encode_obj(k,binary),encode_obj(v,binary))
                              for k,v in py_obj.items()]}
    elif isinstance(py_obj, _uuid.UUID):
        return {'__uuid__': str(py_obj.hex) }
    elif isinstance(py_obj, complex):
        return  {'__complex__': py_obj.__repr__()}
    elif not binary and isinstance(py_obj, bytes):
        return {'__bytes__': tostr(_base64.b64encode(py_obj)) }
    elif binary and isinstance(py_obj, str):
        return {'__string__': tobin(py_obj) }

        
    #Numpy encoding
    elif isinstance(py_obj, _np.ndarray):
        # If the dtype is structured, store the interface description;
        # otherwise, store the corresponding array protocol type string:
        if py_obj.dtype.kind == 'V':
            kind = 'V'
            descr = tobin(py_obj.dtype.descr) if binary else tostr(py_obj.dtype.descr)
        else:
            kind = ''
            descr = tobin(py_obj.dtype.str) if binary else tostr(py_obj.dtype.str)
        data = py_obj.tobytes() if binary else tostr(_base64.b64encode(py_obj.tobytes()))
        return {'__ndarray__': data,
                'dtype': descr,
                'kind': kind,
                'shape': py_obj.shape}
        
    elif isinstance(py_obj, (_np.bool_, _np.number)):
        data = py_obj.tobytes() if binary else tostr(_base64.b64encode(py_obj.tobytes()))
        return {'__npgeneric__': data,
                'dtype': tostr(py_obj.dtype.str)}

    elif callable(py_obj): #functions
        return {'__function__': (py_obj.__module__, py_obj.__name__) }

    return py_obj # assume the bare py_obj is json-able



def decode_obj(json_obj, binary):
    """ 
    Inverse of :func:`encode_obj` that decodes the JSON-compatible `json_obj`
    object into the original Python object that was encoded.

    Parameters
    ----------
    json_obj : object
        The JSON-compabtible object to decode.  Note that this is NOT a JSON
        string, but rather the object that would be decoded from such a string
        (by `json.loads`, for instance).

    binary : bool
        Whether `json_obj` is a binary format or not.  If so, then the decoding
        expects all strings to be binary strings i.e. `b'name'` instead of just
        `'name'`.  The value of this argument should match that used in the 
        original call to :func:`encode_obj`.

    Returns
    -------
    object
        A Python object.
    """
    B = tobin if binary else _ident
    
    if isinstance(json_obj, dict):
        if B('__pygsticlass__') in json_obj:
            modname, clsname = json_obj[B('__pygsticlass__')]
            module = _importlib.import_module(tostr(modname))
            class_ = getattr(module, tostr(clsname))
            return class_
            
        elif B('__pygstiobj__') in json_obj:
            #DEBUG
            #print("DB: creating %s" % str(json_obj['__pygstiobj__']))
            #print("DB: json_obj is type %s with keyvals:" % type(json_obj))
            #for k,v in json_obj.items():
            #    print("%s (%s): %s (%s)" % (k,type(k),v,type(v)))
            
            modname, clsname = json_obj[B('__pygstiobj__')]
            module = _importlib.import_module(tostr(modname))
            class_ = getattr(module, tostr(clsname))

            if B('__init_args__') in json_obj: # construct via __init__
                args = decode_obj(json_obj[B('__init_args__')], binary)
                instance = class_(*args)
                
            else: #init via __new__ and set state
                instance = class_.__new__(class_)

            #Create state dict
            state_dict = {}
            for k,v in json_obj.items():
                if k in (B('__pygstiobj__'),B('__init_args__'),B('__std_base__')): continue
                state_dict[tostr(k)] = decode_obj(v, binary)

            #Set state
            if class_hasattr(instance, '__pygsti_setstate__'):
                instance.__pygsti_setstate__(state_dict)
            elif class_hasattr(instance, '__setstate__'):
                instance.__setstate__(state_dict)
            elif hasattr(instance,'__dict__'): #just update __dict__
                instance.__dict__.update(state_dict)
            elif len(state_dict) > 0:
                raise ValueError("Cannot set nontrivial state of %s object" % type(instance))

            #update instance with std-object info if needed (only if __init__ not called)
            if B('__std_base__') in json_obj:
                decode_std_base(json_obj[B('__std_base__')], instance, binary)

            return instance
        else:
            return decode_std_obj(json_obj, binary)
    else:
        return json_obj

def decode_std_base(json_obj,start,binary):
    """
    Helper to :func:`decode_obj` for decoding pyGSTi objects that are also
    derived from a standard type.
    """
    B = tobin if binary else _ident
    
    if B('__tuple__') in json_obj:
        #OK if __init_args since this means we knew how to construct it (e.g. namedtuples)
        assert(B('__init_args') in json_obj), "No support for sub-classing tuple"
    elif B('__list__') in json_obj:
        for v in json_obj[B('__list__')]:
            start.append(decode_obj(v,binary))
    elif B('__set__') in json_obj:
        for v in json_obj[B('__set__')]:
            start.add(decode_obj(v,binary))
    elif B('__ndict__') in json_obj:
        for k,v in json_obj[B('__ndict__')]:
            start[decode_obj(k,binary)] = decode_obj(v,binary)
    elif B('__odict__') in json_obj:
        for k,v in json_obj[B('__odict__')]:
            start[decode_obj(k,binary)] = decode_obj(v,binary)
    elif B('__uuid__') in json_obj:
        assert(False), "No support for sub-classing UUID"
    elif B('__ndarray__') in json_obj:
        assert(False), "No support for sub-classing ndarray"
    elif B('__npgeneric__') in json_obj:
        assert(False), "No support for sub-classing numpy generics"
    elif B('__complex__') in json_obj:
        assert(False), "No support for sub-classing complex"
    elif B('__counter__') in json_obj:
        assert(False), "No support for sub-classing Counter"
    elif B('__slice__') in json_obj:
        assert(False), "No support for sub-classing slice"
        
def decode_std_obj(json_obj, binary):
    """
    Helper to :func:`decode_obj` that decodes standard (non-pyGSTi) types.
    """
    B = tobin if binary else _ident
    
    if B('__tuple__') in json_obj:
        return tuple([decode_obj(v,binary) for v in json_obj[B('__tuple__')]])
    elif B('__list__') in json_obj:
        return list([decode_obj(v,binary) for v in json_obj[B('__list__')]])
    elif B('__set__') in json_obj:
        return set([decode_obj(v,binary) for v in json_obj[B('__set__')]])
    elif B('__slice__') in json_obj:
        v = json_obj[B('__slice__')]
        return slice(decode_obj(v[0],binary),decode_obj(v[1],binary),
                     decode_obj(v[2],binary))
    elif B('__range__') in json_obj:
        start,stop,step = json_obj[B('__range__')]
        if _sys.version_info >= (3, 0):
            return range(start,stop,step)
        else:
            return list(xrange(start,stop,step)) #lists in python2
    elif B('__ndict__') in json_obj:
        return dict([(decode_obj(k,binary),decode_obj(v,binary))
                     for k,v in json_obj[B('__ndict__')]])
    elif B('__odict__') in json_obj:
        return _collections.OrderedDict(
            [(decode_obj(k,binary),decode_obj(v,binary)) for k,v in json_obj[B('__odict__')]])
    elif B('__odict__') in json_obj:
        return _collections.Counter(
            {decode_obj(k,binary): decode_obj(v,binary) for k,v in json_obj[B('__counter__')]})
    elif B('__uuid__') in json_obj:
        return _uuid.UUID(hex=tostr(json_obj[B('__uuid__')]))
    elif B('__bytes__') in json_obj:
        return json_obj[B('__bytes__')] if binary else \
            _base64.b64decode(json_obj[B('__bytes__')])
    elif B('__string__') in json_obj:
        return tostr(json_obj[B('__string__')]) if binary else \
            json_obj[B('__string__')]
    
    # check for numpy
    elif B('__ndarray__') in json_obj:
        # Check if 'kind' is in json_obj to enable decoding of data
        # serialized with older versions:
        if json_obj[B('kind')] == 'V':
            descr = [tuple(tostr(t) if isinstance(t,bytes) else t for t in d)
                     for d in json_obj[B('dtype')]]
        else:
            descr = json_obj[B('dtype')]
        data = json_obj[B('__ndarray__')] if binary else \
               _base64.b64decode(json_obj[B('__ndarray__')])
        return _np.fromstring(data, dtype=_np.dtype(descr)).reshape(json_obj[B('shape')])
    elif B('__npgeneric__') in json_obj:
        data = json_obj[B('__npgeneric__')] if binary else \
               _base64.b64decode(json_obj[B('__npgeneric__')])
        return _np.fromstring(
            data, dtype=_np.dtype(json_obj[B('dtype')])
        )[0]
    elif B('__complex__') in json_obj:
        return complex(json_obj[B('__complex__')])

    elif B('__function__') in json_obj:
        modname, fnname = json_obj[B('__function__')]
        module = _importlib.import_module(tostr(modname))
        return getattr(module, tostr(fnname))
    
    return json_obj

def tostr(x):
    """
    Python 2 & 3 compatible function for converting a value to the native
    string format.  (In Python 3, bytes need to be decoded.)
    """
    if _sys.version_info >= (3, 0):
        if isinstance(x, bytes):
            return x.decode()
        else:
            return str(x)
    else:
        return x        


def tobin(x):
    """
    Python 2 & 3 compatible function for converting a value to the native
    binary-string ("bytes") format.  (In Python 3, str needs to be encoded.)
    """
    if _sys.version_info >= (3, 0):
        if isinstance(x, str):
            return bytes(x,'utf-8')
        else:
            return x
    else:
        return x        

def _ident(x):
    return x
