"""Structured operational logging with deterministic secret redaction."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
SECRET_NAMES=("api_key","token","secret","password","authorization","credential")
def _redact(obj:Any)->Any:
    if isinstance(obj,dict): return {k:("[REDACTED]" if any(s in k.lower() for s in SECRET_NAMES) else _redact(v)) for k,v in sorted(obj.items())}
    if isinstance(obj,list): return [_redact(v) for v in obj]
    return obj
def log_record(*, execution_id:str, stage:str, severity:str, event_code:str, context:dict[str,Any]|None=None, exception:BaseException|None=None, timestamp:str|None=None)->dict[str,Any]:
    rec={"timestamp":timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"execution_id":execution_id,"stage":stage,"severity":severity,"event_code":event_code,"context":_redact(context or {})}
    if exception: rec["exception"]={"type":type(exception).__name__,"message":str(exception)}
    return rec
