""" Dynamic C++ bindings generator.
"""

import sys, string


### PyPy has 'cppyy' builtin (if enabled, that is)
if 'cppyy' in sys.builtin_module_names:
   _builtin_cppyy = True

   import imp
   sys.modules[ __name__ ] = \
      imp.load_module( 'cppyy', *(None, 'cppyy', ('', '', imp.C_BUILTIN) ) )
   del imp

   _thismodule = sys.modules[ __name__ ]
   _backend = _thismodule.gbl
   _thismodule._backend = _backend

   # custom behavior that is not yet part of PyPy's cppyy
   def _CreateScopeProxy( self, name ):
      return getattr( self, name )
   type(_backend).CreateScopeProxy = _CreateScopeProxy

   def _LookupCppEntity( self, name ):
      return getattr( self, name )
   type(_backend).LookupCppEntity = _LookupCppEntity

   class _Double(float): pass
   type(_backend).Double = _Double

   del _Double, _LookupCppEntity, _CreateScopeProxy

else:
   _builtin_cppyy = False

   # load CPyCppyy C++ extension module, special case for linux and Sun
   needsGlobal =  ( 0 <= sys.platform.find( 'linux' ) ) or\
                  ( 0 <= sys.platform.find( 'sunos' ) )
   if needsGlobal:
      # change dl flags to load dictionaries from pre-linked .so's
      dlflags = sys.getdlopenflags()
      sys.setdlopenflags( 0x100 | 0x2 )    # RTLD_GLOBAL | RTLD_NOW

   import ctypes
   c = ctypes.CDLL("libcppyy_backend.so", ctypes.RTLD_GLOBAL )
   import libcppyy as _backend
   _backend.cpp_backend = c

   # reset dl flags if needed
   if needsGlobal:
      sys.setdlopenflags( dlflags )
   del needsGlobal

if not _builtin_cppyy:
   _backend.SetMemoryPolicy( _backend.kMemoryStrict )

### -----------------------------------------------------------------------------
### -- metaclass helper from six ------------------------------------------------
### -- https://bitbucket.org/gutworth/six/src/8a545f4e906f6f479a6eb8837f31d03731597687/six.py?at=default#cl-800
#
# Copyright (c) 2010-2015 Benjamin Peterson
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

def with_metaclass(meta, *bases):
    """Create a base class with a metaclass."""
    # This requires a bit of explanation: the basic idea is to make a dummy
    # metaclass for one level of class instantiation that replaces itself with
    # the actual metaclass.
    class metaclass(meta):
        def __new__(cls, name, this_bases, d):
            return meta(name, bases, d)
    return type.__new__(metaclass, 'temporary_class', (), {})

### -----------------------------------------------------------------------------

### template support ------------------------------------------------------------
if not _builtin_cppyy:
   class Template:
      def __init__( self, name ):
         self.__name__ = name

      def __repr__(self):
         return "<cppyy.Template '%s' object at %s>" % (self.__name__, hex(id(self)))

      def __call__( self, *args ):
         newargs = [ self.__name__[ 0 <= self.__name__.find( 'std::' ) and 5 or 0:] ]
         for arg in args:
            if type(arg) == str:
               arg = ','.join( map( lambda x: x.strip(), arg.split(',') ) )
            newargs.append( arg )
         result = _backend.MakeCppTemplateClass( *newargs )

       # special case pythonization (builtin_map is not available from the C-API)
         if 'push_back' in result.__dict__:
            def iadd( self, ll ):
               [ self.push_back(x) for x in ll ]
               return self

            result.__iadd__ = iadd

         return result

   _backend.Template = Template


#--- LoadDictionary function and aliases -----------------------------
def load_reflection_info(name):
   sc = gbl.gSystem.Load(name)
   if sc == -1: raise RuntimeError("error loading reflection info")


#--- Other functions needed -------------------------------------------
if not _builtin_cppyy:
   class _ns_meta( type ):
      def __getattr__( cls, name ):
         try:
            attr = _backend.LookupCppEntity( name )
         except TypeError as e:
            raise AttributeError(str(e))
         if type(attr) is _backend.PropertyProxy:
            setattr( cls.__class__, name, attr )
            return attr.__get__(cls)
         setattr( cls, name, attr )
         return attr

   class _stdmeta( type ):
      def __getattr__( cls, name ):   # for non-templated classes in std
         try:
            klass = _backend.CreateScopeProxy( name, cls )
         except TypeError as e:
            raise AttributeError(str(e))
         setattr( cls, name, klass )
         return klass

   class _global_cpp( with_metaclass( _ns_meta ) ):
      class std( with_metaclass( _stdmeta, object ) ):
         string = _backend.CreateScopeProxy( 'string' )

   addressof = _backend.addressof          # cppyy-style

else:
   _global_cpp = _backend
 
def add_smart_pointer(typename):
   """Add a smart pointer to the list of known smart pointer types.
   """
   _backend.AddSmartPtrType(typename)

#--- Global namespace and global objects -------------------------------
gbl  = _global_cpp
sys.modules['cppyy.gbl'] = gbl


#--- Copy over locally defined names ------------------------------------
if _builtin_cppyy:
   for name in dir():
      if name[0] != '_': setattr( _thismodule, name, eval(name) )

#--- Compatibility ------------------------------------------------------
if not _builtin_cppyy:
   bind_object = _backend.BindObject

#--- Pythonization factories --------------------------------------------
import _pythonization
_pythonization._set_backend( _backend )
from _pythonization import *
del _pythonization

#--- CFFI style ---------------------------------------------------------
def cppdef( src ):
   gbl.gInterpreter.Declare( src )

#--- Enable Autoloading ignoring possible error for the time being
try:    gbl.gInterpreter.EnableAutoLoading()
except: pass
