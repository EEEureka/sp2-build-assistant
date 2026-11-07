"""Durable append-only hash-chain journal; pending writes are never silently replayed."""
from pathlib import Path
import json
import os
from .reference_storage import ReferenceError, canonical, digest, utc_now


def read(path):
    target=Path(path)
    if not target.exists():return []
    entries=[]; previous=None
    try:
        with target.open(encoding="utf-8") as stream:
            for index,line in enumerate(stream):
                record=json.loads(line)
                body={k:v for k,v in record.items() if k!="entryHash"}
                if record.get("sequence")!=index or record.get("previousHash")!=previous or record.get("entryHash")!=digest(body):
                    raise ReferenceError("journal_corrupt","Journal chain validation failed",line=index+1)
                entries.append(record);previous=record["entryHash"]
    except (OSError,ValueError) as exc:
        raise ReferenceError("journal_corrupt","Cannot read complete journal; preserve it for reconciliation",reason=str(exc)) from exc
    return entries


def append(path,event,**data):
    target=Path(path).resolve();target.parent.mkdir(parents=True,exist_ok=True)
    lock=Path(str(target)+".lock")
    try: descriptor=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as exc:
        raise ReferenceError("journal_busy","Journal has an active or interrupted writer; inspect the lock before recovery",path=str(lock)) from exc
    try:
        os.close(descriptor)
        entries=read(target)
        record={"schemaVersion":1,"sequence":len(entries),"previousHash":entries[-1]["entryHash"] if entries else None,
                "at":utc_now(),"event":event,**data}
        record["entryHash"]=digest(record)
        with target.open("a",encoding="utf-8",newline="\n") as stream:
            stream.write(canonical(record)+"\n");stream.flush();os.fsync(stream.fileno())
        return record
    finally:lock.unlink(missing_ok=True)


def status(path):
    entries=read(path)
    completed={e["requestId"] for e in entries if e["event"] in ("write_completed","write_failed","write_rejected")}
    pending=[e for e in entries if e["event"]=="write_prepared" and e["requestId"] not in completed]
    last=entries[-1] if entries else None
    return {"journalPath":str(Path(path).resolve()),"entryCount":len(entries),"headHash":last["entryHash"] if last else None,
            "state":last.get("state","planned") if last else "planned","pendingWrites":pending,"entries":entries}
