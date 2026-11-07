"""Reviewed identifier migration with the current native lexical rules."""
import re
from .geometry import GeometryError

_TOKENS=re.compile(r'"(?:\\.|[^"\\])*"|(?:v:)?[A-z_][A-z_0-9]*|.',re.S)

def rename_identifier(expression,old,new):
    if not isinstance(expression,str) or not re.fullmatch(r'[A-z_][A-z_0-9]*',new):
        raise GeometryError('Explicit migration needs native expression text and one valid new identifier')
    result=[];previous=''
    tokens=list(_TOKENS.finditer(expression))
    for i,match in enumerate(tokens):
        text=match.group();name=text[2:] if text.startswith('v:') else text
        next_=next((m.group() for m in tokens[i+1:] if not m.group().isspace()),None)
        is_name=bool(re.fullmatch(r'(?:v:)?[A-z_][A-z_0-9]*',text))
        if is_name and name==old and previous!='.' and (next_!='(' or text.startswith('v:')):
            result.append(('v:' if text.startswith('v:') else '')+new)
        else:result.append(text)
        if not text.isspace():previous=text
    return ''.join(result)
