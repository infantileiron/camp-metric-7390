from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from src.models.entities import Metric,Fact
from src.services import ledger as led
from src.services.business import dump

def save_metric(s,data,i=None):
 r=s.get(Metric,i) if i else Metric()
 if not r:raise HTTPException(404,'口径版本不存在')
 if r.locked:raise HTTPException(409,'已签核口径不可覆盖，请建立新版本')
 for k,v in data.model_dump(mode='json').items():setattr(r,k,v)
 s.add(r)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'相同指标代码和版本已存在')
 return r

def save_fact(s,data,u,i=None):
 led.lock(s)
 r=s.get(Fact,i) if i else Fact()
 if not r:raise HTTPException(404,'班级日事实不存在')
 if i and r.voided:raise HTTPException(409,'事实已作废，请先恢复再修订')
 before=dump(r) if i else None
 for k,v in data.model_dump(mode='json').items():setattr(r,k,v)
 s.add(r)
 try:
  s.flush()
  ledger=led.current(s)
  if ledger:led.record(s,ledger,r.id,'add' if i is None else 'correct',before,dump(r),u.email)
  s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'相同班级与日期已有事实，请修订原记录')
 return r

def set_void(s,u,i,voided):
 led.lock(s)
 r=s.get(Fact,i)
 if not r:raise HTTPException(404,'班级日事实不存在')
 ledger=led.current(s)
 if not ledger or ledger.state!='ready':raise HTTPException(409,'修订账尚未就绪，请先在修订追溯页完成建账')
 if r.voided==voided:raise HTTPException(409,'事实已作废，无需重复作废' if voided else '事实未作废，无需恢复')
 before=dump(r);r.voided=voided;s.add(r);s.flush()
 led.record(s,ledger,r.id,'void' if voided else 'restore',before if voided else None,None if voided else dump(r),u.email)
 s.commit();return r
