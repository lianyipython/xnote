#coding=utf-8

'''
    Tornado template wrapper
    @since 2016/12/05
'''

import web

from tornado.template import Template, Loader
from util import dateutil

import config
import xauth

TEMPLATE_DIR = config.HANDLERS_DIR
NAMESPACE    = dict(
    format_date = dateutil.format_date,
    format_time = dateutil.format_time
)    

_loader = Loader(TEMPLATE_DIR, namespace = NAMESPACE)
_hooks = []

def set_loader_namespace(namespace):
    """ set basic namespace """
    _loader.namespace = namespace

def add_render_hook(hook):
    _hooks.append(hook)

def pre_render(kw):
    """ Main hook for template engine """
    kw["_full_search"] = False
    kw["_search_type"] = "normal"
    # TODO prevent hack
    kw["_is_admin"] = xauth.is_admin()
    kw["_has_login"] = xauth.has_login()
    
def render(template_name, **kw):
    nkw = {}
    pre_render(nkw)
    nkw.update(kw)
    return _loader.load(template_name).generate(**nkw)

def render_text(text, **kw):
    nkw = {}
    pre_render(nkw)
    nkw.update(kw)
    # TODO 需要优化
    template = Template(text, name="<string>", loader=_loader)
    return template.generate(**nkw)

    
def get_code(name):
    return _loader.load(name).code
    
    
def reload():
    global _loader
    _loader = Loader(TEMPLATE_DIR, namespace = NAMESPACE)