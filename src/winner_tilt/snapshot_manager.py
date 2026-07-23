"""Immutable deterministic snapshot manager."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import hashlib,json

def canonical_json(obj: Any) -> str: return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str)
def sha256(obj: Any) -> str: return hashlib.sha256(canonical_json(obj).encode()).hexdigest()
@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id:str; dataset_type:str; content_sha256:str; metadata_sha256:str; acquisition_timestamp:str; publication_timestamp:str|None; effective_timestamp:str; cutoff_timestamp:str; source_references:tuple[str,...]; schema_version:str="1.0.0"
    def to_dict(self): return self.__dict__ | {"source_references":list(self.source_references)}
class SnapshotIntegrityError(ValueError): pass
class SnapshotManager:
    def __init__(self): self._manifest:dict[str,SnapshotRecord]={}; self._content:dict[str,str]={}
    @property
    def manifest(self): return dict(self._manifest)
    def create_snapshot(self,dataset_type:str,payload:Any,*,acquisition_timestamp:str,publication_timestamp:str|None,effective_timestamp:str,cutoff_timestamp:str,source_references:list[str]) -> SnapshotRecord:
        content=canonical_json(payload); ch=hashlib.sha256(content.encode()).hexdigest(); sid=sha256({"dataset_type":dataset_type,"content_sha256":ch,"effective_timestamp":effective_timestamp,"cutoff_timestamp":cutoff_timestamp})[:32]
        if sid in self._manifest:
            if self._content[sid]!=content: raise SnapshotIntegrityError("SNAPSHOT_ID_COLLISION")
            return self._manifest[sid]
        rec=SnapshotRecord(sid,dataset_type,ch,"",acquisition_timestamp,publication_timestamp,effective_timestamp,cutoff_timestamp,tuple(source_references))
        rec=SnapshotRecord(**(rec.to_dict() | {"metadata_sha256":sha256(rec.to_dict() | {"metadata_sha256":""})}))
        self._manifest[sid]=rec; self._content[sid]=content; return rec
    def verify_integrity(self,record:SnapshotRecord,payload:Any)->bool:
        if record.snapshot_id not in self._manifest: raise SnapshotIntegrityError("UNKNOWN_SNAPSHOT")
        if self._manifest[record.snapshot_id]!=record: raise SnapshotIntegrityError("MUTATED_MANIFEST_RECORD")
        if hashlib.sha256(canonical_json(payload).encode()).hexdigest()!=record.content_sha256: raise SnapshotIntegrityError("CONTENT_HASH_MISMATCH")
        return True
    def decision_journal_source_reference(self,record:SnapshotRecord)->dict[str,Any]: return {"snapshot_id":record.snapshot_id,"content_sha256":record.content_sha256,"source_references":list(record.source_references),"schema_version":record.schema_version}
