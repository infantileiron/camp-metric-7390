from datetime import datetime,timezone
from sqlalchemy import text,func
from src.models.entities import Ledger,Revision,Fact
from src.services.business import dump
LOCK_KEY=731511
def now():return datetime.now(timezone.utc).isoformat()
def lock(s):
 # 建账与事实写入共用同一事务级咨询锁，串行化登记顺序，保证衔接并发修改不漏项
 if s.bind.dialect.name=='postgresql':s.execute(text('SELECT pg_advisory_xact_lock(:k)'),{'k':LOCK_KEY})
def current(s):return s.query(Ledger).order_by(Ledger.id).first()
def next_seq(s,ledger_id):return (s.query(func.max(Revision.seq)).filter(Revision.ledger_id==ledger_id).scalar() or 0)+1
def record(s,ledger,fact_id,action,before,after,actor):
 # before/after为事实完整值或None（无有效行）；登记序号在锁内连续分配，提交顺序即登记顺序
 ref=after or before
 s.add(Revision(seq=next_seq(s,ledger.id),ledger_id=ledger.id,fact_id=fact_id,action=action,class_code=ref['class_code'],day=ref['day'],before=before,after=after,actor=actor,created=now()))
def build(s,u):
 lock(s)
 ledger=current(s)
 if ledger:return ledger,False
 ledger=Ledger(state='preparing',created=now(),created_by=u.email);s.add(ledger);s.flush()
 for f in s.query(Fact).order_by(Fact.id).all():record(s,ledger,f.id,'add',None,dump(f),u.email)
 ledger.state='ready';s.commit();return ledger,True
def status(s):
 ledger=current(s)
 if not ledger:return None
 count=s.query(Revision).filter(Revision.ledger_id==ledger.id).count()
 max_seq=s.query(func.max(Revision.seq)).filter(Revision.ledger_id==ledger.id).scalar() or 0
 return {**dump(ledger),'entries':count,'max_seq':max_seq}
def entries_upto(s,ledger_id,cutoff):
 return s.query(Revision).filter(Revision.ledger_id==ledger_id,Revision.seq<=cutoff).order_by(Revision.seq).all()
def rebuild(entries):
 # 按登记顺序回放：after为None（作废）则移除，否则以after全量覆盖；跨日更正以最新业务日期为准，不残留旧行
 state={}
 for e in entries:
  if e.after is None:state.pop(e.fact_id,None)
  else:state[e.fact_id]=e.after
 return [state[k] for k in sorted(state)]
