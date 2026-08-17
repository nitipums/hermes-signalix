--
-- PostgreSQL database dump
--

\restrict HFuvhPuKoXi4eHSvaophV1dGhxQskFptchNIylepxFTBE2PgzH7HnZ3SEWyNzwS

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: daily_scan_observations; Type: TABLE; Schema: public; Owner: signalix
--

CREATE TABLE public.daily_scan_observations (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    symbol text NOT NULL,
    classification text NOT NULL,
    classification_reason text,
    conditions_met integer,
    trend_template_pass boolean,
    rs_rating double precision,
    readiness_status text,
    last_market_date date,
    raw_payload jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.daily_scan_observations OWNER TO signalix;

--
-- Name: daily_scan_runs; Type: TABLE; Schema: public; Owner: signalix
--

CREATE TABLE public.daily_scan_runs (
    id uuid NOT NULL,
    scan_date date NOT NULL,
    run_timestamp timestamp with time zone NOT NULL,
    scanner_version text NOT NULL,
    source_lineage jsonb NOT NULL,
    retry_of_run_id uuid,
    evaluated_symbol_count integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT daily_scan_runs_evaluated_symbol_count_check CHECK ((evaluated_symbol_count >= 0))
);


ALTER TABLE public.daily_scan_runs OWNER TO signalix;

--
-- Name: daily_scan_observations daily_scan_observations_pkey; Type: CONSTRAINT; Schema: public; Owner: signalix
--

ALTER TABLE ONLY public.daily_scan_observations
    ADD CONSTRAINT daily_scan_observations_pkey PRIMARY KEY (id);


--
-- Name: daily_scan_observations daily_scan_observations_run_id_symbol_key; Type: CONSTRAINT; Schema: public; Owner: signalix
--

ALTER TABLE ONLY public.daily_scan_observations
    ADD CONSTRAINT daily_scan_observations_run_id_symbol_key UNIQUE (run_id, symbol);


--
-- Name: daily_scan_runs daily_scan_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: signalix
--

ALTER TABLE ONLY public.daily_scan_runs
    ADD CONSTRAINT daily_scan_runs_pkey PRIMARY KEY (id);


--
-- Name: daily_scan_observations_run_id_idx; Type: INDEX; Schema: public; Owner: signalix
--

CREATE INDEX daily_scan_observations_run_id_idx ON public.daily_scan_observations USING btree (run_id);


--
-- Name: daily_scan_runs_scan_date_idx; Type: INDEX; Schema: public; Owner: signalix
--

CREATE INDEX daily_scan_runs_scan_date_idx ON public.daily_scan_runs USING btree (scan_date, run_timestamp DESC);


--
-- Name: daily_scan_observations daily_scan_observations_immutable; Type: TRIGGER; Schema: public; Owner: signalix
--

CREATE TRIGGER daily_scan_observations_immutable BEFORE DELETE OR UPDATE ON public.daily_scan_observations FOR EACH ROW EXECUTE FUNCTION public.daily_scan_history_reject_mutation();


--
-- Name: daily_scan_runs daily_scan_runs_immutable; Type: TRIGGER; Schema: public; Owner: signalix
--

CREATE TRIGGER daily_scan_runs_immutable BEFORE DELETE OR UPDATE ON public.daily_scan_runs FOR EACH ROW EXECUTE FUNCTION public.daily_scan_history_reject_mutation();


--
-- Name: daily_scan_observations daily_scan_observations_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: signalix
--

ALTER TABLE ONLY public.daily_scan_observations
    ADD CONSTRAINT daily_scan_observations_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.daily_scan_runs(id) ON DELETE RESTRICT;


--
-- Name: daily_scan_runs daily_scan_runs_retry_of_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: signalix
--

ALTER TABLE ONLY public.daily_scan_runs
    ADD CONSTRAINT daily_scan_runs_retry_of_run_id_fkey FOREIGN KEY (retry_of_run_id) REFERENCES public.daily_scan_runs(id);


--
-- PostgreSQL database dump complete
--

\unrestrict HFuvhPuKoXi4eHSvaophV1dGhxQskFptchNIylepxFTBE2PgzH7HnZ3SEWyNzwS

