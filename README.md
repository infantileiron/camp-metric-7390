# 启航 · 训练营指标口径签核

把经营指标从口头约定变为可试算、可比较、可签核冻结的版本记录。

## 真实业务场景

启航训练营经营分析组服务四个线上/线下班级，每天收到班主任的 `启航_班级日报_20261115.xlsx`。原流程由分析员在工作簿计算实到率、结课达成率、退款占比，再把数字抄入经营会纪要。痛点是分子分母的过滤范围不一致、修改公式后旧结论失去依据、数据更正与口径变化无法分清。本项目接收上游班级日事实，替代口径登记/试算/差异解释，给下游经营负责人提供冻结依据。

三个业务实体：指标定义Metric（代码+版本唯一）、班级日事实Fact（班级+日期唯一）、试算签核快照Snapshot；另有事实修订账Ledger/修订条目Revision与追溯试算Retrial，经营会可复现当时收到的日报。五页是口径目录、事实校验、口径试算、签核历史和修订追溯；另有登录。后台worker真实计算，签核锁定口径与意见，后续事实修改不改变历史快照。

|角色|权限|典型动作|
|---|---|---|
|admin|全部业务、审计、独占签核|冻结经营依据|
|analyst|口径/事实读写、试算、业务解释、导出|建立净实到结课率v2并比较v1|
|viewer|业务只读及导出|下载签核快照，后端拒绝写入和任务提交|

## 快速启动

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

前端 [localhost:18210](http://localhost:18210)，后端 [localhost:19210/docs](http://localhost:19210/docs)，PostgreSQL端口17710。账号为 `admin@demo.local` / `analyst@demo.local` / `viewer@demo.local`，密码均 `Demo123!`。`SEED_DEMO=true`启动自动seed，手动重复不会新增同自然键或覆盖人工修订。种子为四班30日共120条事实（2026-10-17至11-15）、三类口径v1和三账号。

## 一天工作剧本

1. 08:50 viewer查看四班的报名/实到/结课/退款人次。
2. 09:00 analyst核对QH-01的2026-11-15事实，满足结课≤实到≤报名、退款≤报名。
3. 09:05 在修订追溯建立事实修订账：现有事实按登记顺序记为初始新增，账从准备到就绪，重试不重复记账。
4. 09:10 在事实校验录入新的班级日事实；修订时填写记录ID及完整字段。建账后新增/更正与记账同事务生效，作废、恢复在事实行一键操作并留痕。
5. 09:20 对completion v1（completed / attended）提交2026-10-17至11-15试算，刷新得到基线。
6. 09:30 在口径目录创建completion v2，分子completed，分母attended-refunds，写明“净实到”业务解释。
7. 09:40 新建v2试算，选择v1成功快照作为基线，核对比值差异、变更字段、日期窗和事实checksum。
8. 09:50 经营会质疑11-15日报，在修订追溯按当时登记截止点发起追溯试算，按业务日期重算原口径，下载JSON留重建依据。
9. 10:00 在签核历史填写不少于8字的解释，说明是否同时存在事实变化。
10. 10:10 admin签核；该版本不可覆盖。10:20 viewer下载 `camp-metric-<id>.json`。

## 指标计算与安全白名单

允许字段为 enrolled/attended/completed/refunds，分别是班级日的报名/实到/结课/退款人次。表达式仅允许数字、字段、括号、+ − * /和一元正负；AST逐节点解释，禁止函数、属性访问、下标、幂运算、布尔、SQL和任意代码执行。表达式最多200字符/60个AST节点，常量绝对值≤1000000；非有限值、行级除零、极小分母造成超限结果显式失败。

按日期窗过滤事实，再按分子与分母各自的授课方式过滤；每行执行对应表达式，分子求和/分母求和，得到ratio。页面乘100展示百分比；不是日比率的简单平均。例如两班结课6/5、实到8/10，合计为11/18；v2扣除退款1/2后是11/15，绝对差11/90。分子分母过滤不同可能超过100%或为负，需人工解释，不自动截断。

外层总分母为0，value=null并显示undefined，不伪装0，可导出诊断但禁止签核。没有事实、非法行表达式使任务failed，修正后重新试算。每次冻结口径、事实、基线、日期窗及checksum。版本比较仅允许同指标代码，显示字段变化、绝对比值差和日期/事实是否一致；数据改变时不能把全部差异归因于口径。

签核需要已成功、非undefined、业务解释至少8字且口径仍与试算一致；试算后修订口径必须重算。签核后锁定口径版本和意见，事实更正不改旧快照。已有冻结版本可再次以新事实试算，但仍保留各次输入。

## 事实修订账与追溯试算

修订账记录事实的新增、更正、作废、恢复四类条目，每条保留业务日期、前后完整值、操作人与登记序号。建账把现有事实按登记顺序记为初始新增，状态从准备到就绪；建账与事实写入共用事务级咨询锁串行衔接，并发修改不漏项，建账可重试且不重复记账。建账后事实保存与记账在同一事务，一起成功或都不生效；建账前的修订仍覆盖旧值且不留痕，账页有明确提示。

追溯试算按登记截止点回放修订账重建事实：新增/更正/恢复以登记值全量覆盖，跨日更正只保留最新业务日期行、不残留旧行，作废不计入；再按业务日期与口径原表达式重算指标，得到整体比值与逐日明细。登记序号在锁内连续分配，已提交条目恒为完整前缀，追溯读取与落库共用同一完整截止点。截止点超出当前登记进度、账未就绪或重建后窗内无有效事实均明确拒绝，不伪造历史。普通试算与签核快照同样排除作废事实。

修订追溯页可查每个条目的前后值、作废与恢复标记，按截止点发起追溯试算并下载 `camp-retro-<id>.json`，文件含截止点、回放条目数、事实checksum与重建后事实明细作为重建依据。作废/恢复需账就绪后进行；观察员只读与导出，不能建账、作废或提交追溯。

## 工程、本地开发与范围

|层|技术|
|---|---|
|前端|原生ES modules/HTML/CSS，Nginx1.27|
|后端|Python3.11/FastAPI/SQLAlchemy/PyJWT|
|异步|Redis7队列，独立Python worker，心跳健康检查|
|数据库|PostgreSQL16，命名数据卷|

backend等待db/redis健康，worker再等backend，frontend等backend；恰好五服务。数据库、Redis及共享`/artifacts`结果卷持久化。Nginx `/api/`代理到后端根路由。清理用 `docker compose down -v --remove-orphans`。显式网络10.253.111.0/24规避当前机器默认地址池耗尽，可用NETWORK_SUBNET改。

环境变量见.env.example：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、DB_PASSWORD、JWT_SECRET、SEED_DEMO、NETWORK_SUBNET。演示凭据/密钥部署时替换。本地开发先起db/redis，backend安装requirements，设置DATABASE_URL/REDIS_URL/JWT_SECRET后 `uvicorn src.main:app --reload`；前端保留同源Nginx或开发代理。

目录按backend/src的routes/controllers/services/models/schemas/middlewares/config/utils及frontend/src的api/stores/pages/components/hooks/utils/constants/types/router拆分。共享表格、字段、状态标签；表单hooks与HTML转义；请求ID/安全头中间件、业务审计和全局错误处理。枚举ROLES/STATES/MODES/APPROVALS/FIELDS/ACTIONS/LEDGER_STATES位于后端constants/enums.py、schemas/business.py和前端constants/enums.js。ORM建初表，migrations/001_initial.sql与002_revision_ledger.sql保留实际DDL；无在线版本迁移执行器，既有库按002手工补列建表或重建数据卷。

小型范围：逐条表单/API录入，无Excel批导、删除、分页或跨指标引用；单worker，启动恢复待处理任务。班级日事实是人次，不能解释为去重学员留存。签核只在站内，不外发邮件/电子签章。Google Fonts依赖网络，离线回退serif/sans-serif。测试证据在 `../../test-artifacts/gb-3111/TESTING.md`，源码无截图/日志。MIT License见LICENSE。
