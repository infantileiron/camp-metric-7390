import os,json
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy import func
from src.config.database import db
from src.models.entities import User,Metric,Fact,Snapshot,Audit,Revision,Retrial
from src.schemas.business import Login,MetricInput,FactInput,RunInput,NoteInput,RetrialInput
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump
from src.services.repository import save_metric,save_fact,set_void
from src.services.analysis import calculate_retro
from src.services import ledger as led
from src.controllers import business as ensure
router=APIRouter()
@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
@router.get('/metrics')
def metrics(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Metric).order_by(Metric.code,Metric.version).all()]
@router.post('/metrics')
def create_metric(data:MetricInput,u=Depends(editor),s=Depends(db)):
 r=save_metric(s,data);audit(s,u,'建立口径 '+r.code+' v'+str(r.version));return dump(r)
@router.put('/metrics/{i}')
def edit_metric(i:int,data:MetricInput,u=Depends(editor),s=Depends(db)):
 r=save_metric(s,data,i);audit(s,u,'修订口径 '+str(i));return dump(r)
@router.get('/facts')
def facts(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Fact).order_by(Fact.voided,Fact.day.desc(),Fact.class_code).all()]
@router.post('/facts')
def create_fact(data:FactInput,u=Depends(editor),s=Depends(db)):
 r=save_fact(s,data,u);audit(s,u,'录入事实 '+str(r.id));return dump(r)
@router.put('/facts/{i}')
def edit_fact(i:int,data:FactInput,u=Depends(editor),s=Depends(db)):
 r=save_fact(s,data,u,i);audit(s,u,'修订事实 '+str(i));return dump(r)
@router.post('/facts/{i}/void')
def void_fact(i:int,u=Depends(editor),s=Depends(db)):
 r=set_void(s,u,i,True);audit(s,u,'作废事实 '+str(i));return dump(r)
@router.post('/facts/{i}/restore')
def restore_fact(i:int,u=Depends(editor),s=Depends(db)):
 r=set_void(s,u,i,False);audit(s,u,'恢复事实 '+str(i));return dump(r)
@router.get('/ledger')
def ledger_status(u=Depends(current),s=Depends(db)):return {'ledger':led.status(s)}
@router.get('/ledger/entries')
def ledger_entries(u=Depends(current),s=Depends(db)):
 ledger=led.current(s)
 if not ledger:return []
 return [dump(r) for r in s.query(Revision).filter(Revision.ledger_id==ledger.id).order_by(Revision.seq.desc()).limit(200).all()]
@router.post('/ledger/build')
def ledger_build(u=Depends(editor),s=Depends(db)):
 ledger,created=led.build(s,u)
 if created:audit(s,u,'建立事实修订账 '+str(ledger.id))
 return led.status(s)
@router.post('/retrials')
def retrial(data:RetrialInput,u=Depends(editor),s=Depends(db)):
 m=ensure.metric(s,data.metric_id);ledger=led.current(s)
 if not ledger or ledger.state!='ready':raise HTTPException(409,'修订账尚未就绪，无法追溯试算，请先完成建账')
 max_seq=s.query(func.max(Revision.seq)).filter(Revision.ledger_id==ledger.id).scalar() or 0
 cutoff=data.cutoff_seq if data.cutoff_seq is not None else max_seq
 if cutoff>max_seq:raise HTTPException(409,'登记截止点 '+str(cutoff)+' 超出修订账登记进度（当前到 '+str(max_seq)+'），无法追溯，不伪造历史')
 entries=led.entries_upto(s,ledger.id,cutoff)
 rows=[r for r in led.rebuild(entries) if data.date_from.isoformat()<=r['day']<=data.date_to.isoformat()]
 basis=dict(ledger_id=ledger.id,cutoff_seq=cutoff,max_seq=max_seq,entries_applied=len(entries))
 try:result=calculate_retro(dump(m),rows,basis)
 except ValueError as e:raise HTTPException(409,str(e))
 r=Retrial(metric_id=m.id,ledger_id=ledger.id,cutoff_seq=cutoff,date_from=data.date_from.isoformat(),date_to=data.date_to.isoformat(),result=result,created=led.now(),created_by=u.email)
 s.add(r);s.commit();audit(s,u,'追溯试算 '+str(r.id)+' 截止 '+str(cutoff));return dump(r)
@router.get('/retrials')
def retrials(u=Depends(current),s=Depends(db)):
 out=[]
 for r in s.query(Retrial).order_by(Retrial.id.desc()).limit(100).all():
  d=dump(r);d['result']={k:v for k,v in (r.result or {}).items() if k!='facts'};out.append(d)
 return out
@router.get('/retrials/{i}')
def retrial_detail(i:int,u=Depends(current),s=Depends(db)):
 r=s.get(Retrial,i)
 if not r:raise HTTPException(404,'追溯试算不存在')
 return dump(r)
@router.get('/retrials/{i}/export')
def retrial_export(i:int,u=Depends(current),s=Depends(db)):
 r=s.get(Retrial,i)
 if not r:raise HTTPException(404,'追溯试算不存在')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="camp-retro-{i}.json"'})
@router.get('/snapshots')
def snapshots(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Snapshot).order_by(Snapshot.id.desc()).all()]
@router.post('/snapshots')
def run(data:RunInput,u=Depends(editor),s=Depends(db)):
 m=ensure.metric(s,data.metric_id);baseline=None
 if data.baseline_id:
  b=ensure.snapshot(s,data.baseline_id)
  if b.state!='done':raise HTTPException(409,'仅成功快照可作为比较基线')
  if b.result['metric']['code']!=m.code:raise HTTPException(409,'只能比较同一指标代码的口径版本')
  baseline=dict(id=b.id,date_from=b.date_from,date_to=b.date_to,result={k:b.result[k] for k in ['metric','value','facts_checksum']})
 values=data.model_dump(mode='json');rows=[dump(f) for f in s.query(Fact).filter(Fact.day>=values['date_from'],Fact.day<=values['date_to'],Fact.voided.isnot(True)).order_by(Fact.day,Fact.class_code).all()]
 frozen={'metric':dump(m),'facts':rows,'baseline':baseline,'date_from':values['date_from'],'date_to':values['date_to']}
 r=Snapshot(**values,result={'snapshot':frozen});s.add(r);s.commit()
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('camp:snapshots',r.id)
 except redis.RedisError:r.state='failed';r.error='队列不可用，请恢复后重新试算';s.commit();raise HTTPException(503,r.error)
 audit(s,u,'提交试算 '+str(r.id));return dump(r)
@router.get('/snapshots/{i}')
def detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure.snapshot(s,i))
@router.put('/snapshots/{i}/note')
def note(i:int,data:NoteInput,u=Depends(editor),s=Depends(db)):
 r=ensure.snapshot(s,i)
 if r.state!='done' or r.approval=='approved':raise HTTPException(409,'仅成功且未签核快照可编辑意见')
 r.note=data.note;s.commit();audit(s,u,'起草签核意见 '+str(i));return dump(r)
@router.post('/snapshots/{i}/approve')
def approve(i:int,u=Depends(admin),s=Depends(db)):
 r=ensure.snapshot(s,i)
 if r.state!='done' or r.approval=='approved':raise HTTPException(409,'仅成功且未签核快照可签核')
 if r.result['value'] is None:raise HTTPException(409,'零分母undefined快照不能签核，请修正口径')
 if len(r.note)<8:raise HTTPException(409,'先填写至少8字业务解释')
 m=ensure.metric(s,r.metric_id)
 if any(getattr(m,k)!=v for k,v in r.result['metric'].items() if k not in ['locked']):raise HTTPException(409,'口径在试算后已变更，请用当前版本重新试算再签核')
 r.approval='approved';r.approved_by=u.email;m.locked=True;s.commit();audit(s,u,'签核冻结 '+str(i));return dump(r)
@router.get('/snapshots/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure.snapshot(s,i)
 if r.state!='done':raise HTTPException(409,'仅成功快照可导出')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="camp-metric-{i}.json"'})
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]
