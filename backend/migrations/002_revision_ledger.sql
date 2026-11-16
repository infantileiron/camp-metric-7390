-- 002_revision_ledger.sql — 事实修订账与追溯试算
-- ORM启动时自动建表；本文件保留实际DDL供既有库手工执行，无在线版本迁移执行器。

ALTER TABLE public.facts ADD COLUMN voided boolean NOT NULL DEFAULT false;

CREATE TABLE public.ledgers (
    id serial PRIMARY KEY,
    state character varying(20) NOT NULL DEFAULT 'preparing',
    created character varying(40),
    created_by character varying(100) DEFAULT ''
);

CREATE TABLE public.revisions (
    seq bigint PRIMARY KEY,
    ledger_id integer NOT NULL REFERENCES public.ledgers(id),
    fact_id integer,
    action character varying(20) NOT NULL,
    class_code character varying(50),
    day character varying(10),
    before json,
    after json,
    actor character varying(100),
    created character varying(40)
);

CREATE INDEX revisions_ledger_seq_idx ON public.revisions (ledger_id, seq);

CREATE TABLE public.retrials (
    id serial PRIMARY KEY,
    metric_id integer REFERENCES public.metrics(id),
    ledger_id integer,
    cutoff_seq bigint,
    date_from character varying(10),
    date_to character varying(10),
    result json,
    created character varying(40),
    created_by character varying(100) DEFAULT ''
);
