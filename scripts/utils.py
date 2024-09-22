#!/usr/bin/env python3.8
class Obj(dict):
    def __init__(self, d):
        for a, b in d.items():
            if isinstance(b, (list, tuple)):
                setattr(self, a, [Obj(x) if isinstance(x, dict) else x for x in b])
            else:
                setattr(self, a, Obj(b) if isinstance(b, dict) else b)

def dict_2_obj(d: dict):
    return Obj(d)

def obj_2_dict(obj):
    if isinstance(obj, Obj):
        return {k: obj_2_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [obj_2_dict(x) for x in obj]
    else:
        return obj