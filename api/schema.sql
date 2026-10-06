-- ============================================================================
-- fastapi-rag-agent · 数据库 Schema
-- ============================================================================
--
-- ## ⛔ 本文件是【生成的】，不要手改
--
-- 生成方式（**从活着的数据库导**，不是手写）：
--
--     docker compose exec -T postgres \
--       pg_dump -U postgres -d rag_db --schema-only --no-owner --no-privileges \
--       > api/schema.sql
--
-- 生成时间：2026-09-29
-- 来源数据库：本机开发库（Docker 容器 `postgres-rag`，镜像 `pgvector/pgvector:pg17`）
--
-- ## 为什么要有它
--
-- 在此之前，**本仓的表结构【只存在于代码里】** ——
-- `api/db.py:56-174` 的 `create_table()` 用 `CREATE TABLE IF NOT EXISTS` 在应用启动时建表，
-- 而 **Alembic 只覆盖其中一部分**。⇒ 新人/新环境**没有一个地方能一眼看到全貌**。
-- 决策见 `docs/decisions/DEC-036-文档体系分四层.md`（遗留 #3）。
--
-- ## ⚠️ 三条要紧的
--
-- 1. **它可能与代码不一致** —— 因为 `create_table()` 用的是 `IF NOT EXISTS`，
--    **表已存在时它不会改任何东西**。所以"代码写的"与"库里实际有的"**可能不同步**。
--    📌 **本文件反映的是【库里实际有的】—— 那是更权威的那一份。**
--
-- 2. 🔴 **已知的最典型一处**：`api/db.py:100` 写的是 `USING **ivfflat**`，
--    而**活库里实际是 `USING hnsw`**（见下方 `documents_embedding_idx`）。
--    根因：那个索引**早就存在**（手工建的 hnsw）⇒ 代码那句 `IF NOT EXISTS` **从未生效**。
--    ⇒ **上云首次建表会建出 ivfflat —— 与本机不同。**
--    详见 `docs/契约/数据模型.md` §六。⬜ 待裁。
--
-- 3. **重建时注意**：`pg_dump` 导出的 SQL **不含数据**（`--schema-only`）。
--    恢复数据用 `pg_dump`（不带 `--schema-only`）或卷备份，见 `docs/说明/运维.md` §六。
--
-- ## 相关
--
-- | 文档 | 说明 |
-- |---|---|
-- | `docs/契约/数据模型.md` | **6 张表的逐字段说明**（人读的那份） |
-- | `api/db.py` | 建表代码（`create_table()`） |
-- | `api/alembic/versions/` | 迁移（**只覆盖 3 处，不全**） |
-- | `docs/说明/运维.md` §六 | 备份与恢复 |
--
-- ============================================================================


--
-- PostgreSQL database dump
--

\restrict TUIKOl6jbVxuvXS6rc3Oe4fWWRif74BZcCGcMoePLwQUUq1WfbvSOfGiiNhX5yf

-- Dumped from database version 17.10 (Debian 17.10-1.pgdg12+1)
-- Dumped by pg_dump version 17.10 (Debian 17.10-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_keys (
    id integer NOT NULL,
    user_name text NOT NULL,
    key_hash text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp without time zone NOT NULL,
    is_active integer DEFAULT 1   -- DEC-086：auth.py 按 COALESCE(is_active,1)=1 过滤；写侧是整数 0/1
);


--
-- Name: api_keys_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.api_keys_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: api_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.api_keys_id_seq OWNED BY public.api_keys.id;


--
-- Name: budget_intercepts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.budget_intercepts (
    id integer NOT NULL,
    user_name text NOT NULL,
    tool_name text,
    reason text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: budget_intercepts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.budget_intercepts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: budget_intercepts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.budget_intercepts_id_seq OWNED BY public.budget_intercepts.id;


--
-- Name: cost_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_records (
    id integer NOT NULL,
    user_name text NOT NULL,
    thread_id text DEFAULT 'unknown'::text,
    model text NOT NULL,
    purpose text NOT NULL,
    prompt_tokens integer DEFAULT 0 NOT NULL,
    completion_tokens integer DEFAULT 0 NOT NULL,
    total_tokens integer DEFAULT 0 NOT NULL,
    input_cost real DEFAULT 0.0 NOT NULL,
    output_cost real DEFAULT 0.0 NOT NULL,
    total_cost real DEFAULT 0.0 NOT NULL,
    tool_name text,
    tool_args text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: cost_records_archive; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_records_archive (
    id integer NOT NULL,
    user_name text NOT NULL,
    thread_id text DEFAULT 'unknown'::text,
    model text NOT NULL,
    purpose text NOT NULL,
    prompt_tokens integer DEFAULT 0 NOT NULL,
    completion_tokens integer DEFAULT 0 NOT NULL,
    total_tokens integer DEFAULT 0 NOT NULL,
    input_cost real DEFAULT 0.0 NOT NULL,
    output_cost real DEFAULT 0.0 NOT NULL,
    total_cost real DEFAULT 0.0 NOT NULL,
    tool_name text,
    tool_args text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: cost_records_archive_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cost_records_archive_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cost_records_archive_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cost_records_archive_id_seq OWNED BY public.cost_records_archive.id;


--
-- Name: cost_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cost_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cost_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cost_records_id_seq OWNED BY public.cost_records.id;


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id integer NOT NULL,
    content text NOT NULL,
    source text,
    embedding public.vector(1536),
    requested_by text DEFAULT 'anonymous'::text NOT NULL
);


--
-- Name: documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.documents_id_seq OWNED BY public.documents.id;


--
-- Name: token_usage_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.token_usage_logs (
    id integer NOT NULL,
    user_name text NOT NULL,
    thread_id text DEFAULT 'unknown'::text,
    model text NOT NULL,
    purpose text NOT NULL,
    prompt_tokens integer NOT NULL,
    completion_tokens integer NOT NULL,
    total_tokens integer NOT NULL,
    cost real DEFAULT 0.0 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: token_usage_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.token_usage_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: token_usage_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.token_usage_logs_id_seq OWNED BY public.token_usage_logs.id;


--
-- Name: api_keys id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys ALTER COLUMN id SET DEFAULT nextval('public.api_keys_id_seq'::regclass);


--
-- Name: budget_intercepts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.budget_intercepts ALTER COLUMN id SET DEFAULT nextval('public.budget_intercepts_id_seq'::regclass);


--
-- Name: cost_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_records ALTER COLUMN id SET DEFAULT nextval('public.cost_records_id_seq'::regclass);


--
-- Name: cost_records_archive id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_records_archive ALTER COLUMN id SET DEFAULT nextval('public.cost_records_archive_id_seq'::regclass);


--
-- Name: documents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents ALTER COLUMN id SET DEFAULT nextval('public.documents_id_seq'::regclass);


--
-- Name: token_usage_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_usage_logs ALTER COLUMN id SET DEFAULT nextval('public.token_usage_logs_id_seq'::regclass);


--
-- Name: api_keys api_keys_key_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_key_hash_key UNIQUE (key_hash);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: budget_intercepts budget_intercepts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.budget_intercepts
    ADD CONSTRAINT budget_intercepts_pkey PRIMARY KEY (id);


--
-- Name: cost_records_archive cost_records_archive_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_records_archive
    ADD CONSTRAINT cost_records_archive_pkey PRIMARY KEY (id);


--
-- Name: cost_records cost_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_records
    ADD CONSTRAINT cost_records_pkey PRIMARY KEY (id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: token_usage_logs token_usage_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_usage_logs
    ADD CONSTRAINT token_usage_logs_pkey PRIMARY KEY (id);


--
-- Name: documents_embedding_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX documents_embedding_idx ON public.documents USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: documents_requested_by_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX documents_requested_by_idx ON public.documents USING btree (requested_by);


--
-- Name: idx_cost_records_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cost_records_date ON public.cost_records USING btree (created_at);


--
-- Name: idx_cost_records_purpose; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cost_records_purpose ON public.cost_records USING btree (purpose);


--
-- Name: idx_cost_records_thread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cost_records_thread ON public.cost_records USING btree (thread_id);


--
-- Name: idx_cost_records_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cost_records_user ON public.cost_records USING btree (user_name);


--
-- Name: idx_token_usage_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_token_usage_date ON public.token_usage_logs USING btree (created_at);


--
-- Name: idx_token_usage_thread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_token_usage_thread ON public.token_usage_logs USING btree (thread_id);


--
-- Name: idx_token_usage_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_token_usage_user ON public.token_usage_logs USING btree (user_name);


--
-- PostgreSQL database dump complete
--

\unrestrict TUIKOl6jbVxuvXS6rc3Oe4fWWRif74BZcCGcMoePLwQUUq1WfbvSOfGiiNhX5yf

