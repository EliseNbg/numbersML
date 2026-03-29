--
-- PostgreSQL database dump
--

\restrict kk2Mqcjqi3tJr9k9v3li1gQn5q9BQsy9wMSFzckzbSJcbWfl4MToK62y9XrNq4G

-- Dumped from database version 15.17
-- Dumped by pg_dump version 17.9 (Ubuntu 17.9-0ubuntu0.25.10.1)

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
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: can_handle_more_symbols(integer, numeric); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.can_handle_more_symbols(p_target_time_ms integer DEFAULT 800, p_safety_margin numeric DEFAULT 0.2) RETURNS TABLE(can_add boolean, current_avg_time_ms numeric, available_capacity_ms numeric, recommendation text)
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_current_avg NUMERIC;
    v_available NUMERIC;
BEGIN
    -- Get current average processing time
    SELECT AVG(total_time_ms) INTO v_current_avg
    FROM pipeline_metrics
    WHERE timestamp > NOW() - INTERVAL '5 minutes';
    
    v_current_avg := COALESCE(v_current_avg, 0);
    v_available := p_target_time_ms - v_current_avg;
    
    RETURN QUERY
    SELECT 
        (v_available > (p_target_time_ms * p_safety_margin)) as can_add,
        ROUND(v_current_avg, 2) as current_avg_time_ms,
        ROUND(v_available, 2) as available_capacity_ms,
        CASE 
            WHEN v_available > (p_target_time_ms * 0.5) THEN 'Can add more symbols/indicators'
            WHEN v_available > (p_target_time_ms * 0.2) THEN 'Approaching capacity limit'
            ELSE 'At capacity - reduce symbols/indicators'
        END as recommendation;
END;
$$;


--
-- Name: FUNCTION can_handle_more_symbols(p_target_time_ms integer, p_safety_margin numeric); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.can_handle_more_symbols(p_target_time_ms integer, p_safety_margin numeric) IS 'Capacity planning: check if pipeline can handle more load';


--
-- Name: get_or_create_symbol(text, text, text, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_or_create_symbol(p_symbol text, p_base_asset text, p_quote_asset text, p_exchange text DEFAULT 'binance'::text) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE v_symbol_id INTEGER;
BEGIN
    SELECT id INTO v_symbol_id FROM symbols
    WHERE symbol = p_symbol;

    IF v_symbol_id IS NULL THEN
        INSERT INTO symbols (symbol, base_asset, quote_asset)
        VALUES (p_symbol, p_base_asset, p_quote_asset)
        RETURNING id INTO v_symbol_id;
    END IF;

    RETURN v_symbol_id;
END;
$$;


--
-- Name: get_pipeline_performance(integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_pipeline_performance(p_minutes integer DEFAULT 5) RETURNS TABLE(avg_time_ms numeric, max_time_ms integer, p95_time_ms numeric, p99_time_ms numeric, ticks_processed bigint, sla_violations bigint, compliance_pct numeric)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ROUND(AVG(total_time_ms)::numeric, 2) as avg_time_ms,
        MAX(total_time_ms) as max_time_ms,
        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_time_ms)::numeric, 2) as p95_time_ms,
        ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY total_time_ms)::numeric, 2) as p99_time_ms,
        COUNT(*) as ticks_processed,
        COUNT(*) FILTER (WHERE total_time_ms > 1000) as sla_violations,
        ROUND((COUNT(*) FILTER (WHERE total_time_ms <= 1000)::numeric / COUNT(*) * 100), 2) as compliance_pct
    FROM pipeline_metrics
    WHERE timestamp > NOW() - (p_minutes || ' minutes')::INTERVAL;
END;
$$;


--
-- Name: FUNCTION get_pipeline_performance(p_minutes integer); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.get_pipeline_performance(p_minutes integer) IS 'Get current pipeline performance for last N minutes';


--
-- Name: notify_config_change(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.notify_config_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    PERFORM pg_notify(
        'config_changed',
        json_build_object(
            'config_type', TG_TABLE_NAME,
            'key', NEW.key,
            'value', NEW.value
        )::text
    );
    RETURN NEW;
END;
$$;


--
-- Name: notify_indicator_change(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.notify_indicator_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    PERFORM pg_notify(
        'indicator_changed',
        json_build_object(
            'indicator_name', NEW.name,
            'change_type', TG_OP,
            'version', NEW.version
        )::text
    );
    RETURN NEW;
END;
$$;


--
-- Name: update_1s_candle_timestamp(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_1s_candle_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: update_pipeline_state_timestamp(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_pipeline_state_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: symbols; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.symbols (
    id integer NOT NULL,
    symbol text NOT NULL,
    base_asset text NOT NULL,
    quote_asset text NOT NULL,
    status text DEFAULT 'TRADING'::text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    is_allowed boolean DEFAULT true NOT NULL,
    price_precision integer DEFAULT 8 NOT NULL,
    tick_size numeric(20,10) DEFAULT 0.01 NOT NULL,
    min_price numeric(20,10),
    max_price numeric(20,10),
    quantity_precision integer DEFAULT 8 NOT NULL,
    step_size numeric(20,10) DEFAULT 0.00001 NOT NULL,
    min_quantity numeric(20,10),
    max_quantity numeric(20,10),
    min_notional numeric(20,10) DEFAULT 10.0,
    max_notional numeric(20,10),
    last_price numeric(20,10),
    last_update_id bigint,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    last_sync_at timestamp without time zone,
    is_test boolean DEFAULT false NOT NULL
);


--
-- Name: TABLE symbols; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.symbols IS 'Symbol metadata from Binance exchange';


--
-- Name: COLUMN symbols.is_allowed; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.symbols.is_allowed IS 'EU compliance - allowed for trading';


--
-- Name: COLUMN symbols.tick_size; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.symbols.tick_size IS 'Minimum price increment';


--
-- Name: COLUMN symbols.step_size; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.symbols.step_size IS 'Minimum quantity increment';


--
-- Name: COLUMN symbols.is_test; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.symbols.is_test IS 'Flag for test symbols used in integration tests';


--
-- Name: active_symbols; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.active_symbols AS
 SELECT symbols.id,
    symbols.symbol,
    symbols.base_asset,
    symbols.quote_asset
   FROM public.symbols
  WHERE ((symbols.is_active = true) AND (symbols.is_allowed = true));


--
-- Name: candle_indicators; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.candle_indicators (
    "time" timestamp without time zone NOT NULL,
    symbol_id integer NOT NULL,
    price numeric(20,10) NOT NULL,
    volume numeric(20,10) NOT NULL,
    "values" jsonb DEFAULT '{}'::jsonb NOT NULL,
    indicator_keys text[] NOT NULL,
    indicator_version integer DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE candle_indicators; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.candle_indicators IS 'Calculated indicator values per tick';


--
-- Name: COLUMN candle_indicators."values"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.candle_indicators."values" IS 'JSONB with all indicator values';


--
-- Name: COLUMN candle_indicators.indicator_keys; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.candle_indicators.indicator_keys IS 'Array of indicator keys for fast lookup';


--
-- Name: candles_1s; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.candles_1s (
    "time" timestamp with time zone NOT NULL,
    symbol_id integer NOT NULL,
    open numeric NOT NULL,
    high numeric NOT NULL,
    low numeric NOT NULL,
    close numeric NOT NULL,
    volume numeric DEFAULT 0 NOT NULL,
    quote_volume numeric DEFAULT 0 NOT NULL,
    trade_count integer DEFAULT 0 NOT NULL,
    first_trade_id bigint DEFAULT 0 NOT NULL,
    last_trade_id bigint DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    processed boolean DEFAULT false NOT NULL
);


--
-- Name: collection_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collection_config (
    symbol_id integer NOT NULL,
    collect_ticks boolean DEFAULT false NOT NULL,
    collect_24hr_ticker boolean DEFAULT true NOT NULL,
    collect_orderbook boolean DEFAULT false NOT NULL,
    collect_candles boolean DEFAULT true NOT NULL,
    tick_snapshot_interval_sec integer DEFAULT 1 NOT NULL,
    ticker_snapshot_interval_sec integer DEFAULT 1 NOT NULL,
    orderbook_snapshot_interval_sec integer DEFAULT 1,
    candle_intervals text[] DEFAULT '{1m,5m,15m,1h}'::text[] NOT NULL,
    orderbook_levels integer DEFAULT 10,
    orderbook_storage_mode text DEFAULT 'arrays'::text,
    tick_retention_days integer DEFAULT 30 NOT NULL,
    ticker_retention_days integer DEFAULT 180 NOT NULL,
    orderbook_retention_days integer DEFAULT 30,
    candle_retention_days integer DEFAULT 365 NOT NULL,
    max_price_move_pct numeric(10,4) DEFAULT 10.0,
    max_quantity_move_pct numeric(10,4) DEFAULT 50.0,
    max_gap_seconds integer DEFAULT 5,
    is_allowed boolean DEFAULT true NOT NULL,
    last_region_check timestamp without time zone DEFAULT now(),
    is_collecting boolean DEFAULT false NOT NULL,
    last_config_change timestamp without time zone DEFAULT now() NOT NULL,
    config_version integer DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_orderbook_levels CHECK (((orderbook_levels IS NULL) OR ((orderbook_levels >= 5) AND (orderbook_levels <= 20)))),
    CONSTRAINT chk_retention_days CHECK ((tick_retention_days >= 0)),
    CONSTRAINT chk_tick_interval CHECK ((tick_snapshot_interval_sec >= 1)),
    CONSTRAINT chk_ticker_interval CHECK ((ticker_snapshot_interval_sec >= 1))
);


--
-- Name: TABLE collection_config; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.collection_config IS 'Per-symbol collection configuration';


--
-- Name: COLUMN collection_config.collect_ticks; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.collection_config.collect_ticks IS 'Collect individual trades';


--
-- Name: COLUMN collection_config.collect_24hr_ticker; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.collection_config.collect_24hr_ticker IS 'Collect 24hr ticker stats';


--
-- Name: COLUMN collection_config.is_allowed; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.collection_config.is_allowed IS 'EU compliance flag';


--
-- Name: config_change_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.config_change_log (
    id bigint NOT NULL,
    config_type text NOT NULL,
    config_key text NOT NULL,
    old_value jsonb,
    new_value jsonb NOT NULL,
    changed_by text DEFAULT 'system'::text NOT NULL,
    changed_at timestamp without time zone DEFAULT now() NOT NULL,
    applied_at timestamp without time zone,
    status text DEFAULT 'applied'::text NOT NULL,
    reason text
);


--
-- Name: TABLE config_change_log; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.config_change_log IS 'Audit trail for configuration changes';


--
-- Name: config_change_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.config_change_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: config_change_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.config_change_log_id_seq OWNED BY public.config_change_log.id;


--
-- Name: data_quality_issues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_quality_issues (
    id bigint NOT NULL,
    symbol_id integer NOT NULL,
    issue_type text NOT NULL,
    severity text NOT NULL,
    raw_data jsonb NOT NULL,
    detected_at timestamp without time zone DEFAULT now() NOT NULL,
    resolved boolean DEFAULT false NOT NULL,
    resolved_at timestamp without time zone,
    resolution_notes text
);


--
-- Name: TABLE data_quality_issues; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.data_quality_issues IS 'Data quality issues and anomalies';


--
-- Name: COLUMN data_quality_issues.severity; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.data_quality_issues.severity IS 'warning, error, or critical';


--
-- Name: data_quality_issues_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.data_quality_issues_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: data_quality_issues_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.data_quality_issues_id_seq OWNED BY public.data_quality_issues.id;


--
-- Name: data_quality_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_quality_metrics (
    id bigint NOT NULL,
    symbol_id integer NOT NULL,
    date date NOT NULL,
    hour integer NOT NULL,
    ticks_received bigint DEFAULT 0 NOT NULL,
    ticks_validated bigint DEFAULT 0 NOT NULL,
    ticks_rejected bigint DEFAULT 0 NOT NULL,
    anomalies_detected bigint DEFAULT 0 NOT NULL,
    gaps_detected bigint DEFAULT 0 NOT NULL,
    gaps_filled bigint DEFAULT 0 NOT NULL,
    quality_score numeric(5,2),
    quality_level text,
    latency_avg_ms numeric(10,2),
    latency_p50_ms numeric(10,2),
    latency_p95_ms numeric(10,2),
    latency_p99_ms numeric(10,2),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE data_quality_metrics; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.data_quality_metrics IS 'Hourly data quality metrics';


--
-- Name: COLUMN data_quality_metrics.quality_level; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.data_quality_metrics.quality_level IS 'excellent, good, fair, or poor';


--
-- Name: data_quality_metrics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.data_quality_metrics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: data_quality_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.data_quality_metrics_id_seq OWNED BY public.data_quality_metrics.id;


--
-- Name: indicator_definitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.indicator_definitions (
    id bigint NOT NULL,
    name text NOT NULL,
    class_name text NOT NULL,
    module_path text NOT NULL,
    category text NOT NULL,
    description text,
    params jsonb DEFAULT '{}'::jsonb NOT NULL,
    params_schema jsonb NOT NULL,
    code_hash text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by text DEFAULT 'system'::text,
    updated_by text
);


--
-- Name: TABLE indicator_definitions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.indicator_definitions IS 'Dynamic indicator definitions';


--
-- Name: indicator_definitions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.indicator_definitions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: indicator_definitions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.indicator_definitions_id_seq OWNED BY public.indicator_definitions.id;


--
-- Name: latest_indicators; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.latest_indicators AS
 SELECT DISTINCT ON (ti.symbol_id) s.symbol,
    ti."time",
    ti.price,
    ti.volume,
    ti."values",
    ti.indicator_keys
   FROM (public.candle_indicators ti
     JOIN public.symbols s ON ((s.id = ti.symbol_id)))
  WHERE ((s.is_active = true) AND (s.is_allowed = true))
  ORDER BY ti.symbol_id, ti."time" DESC;


--
-- Name: ticker_24hr_stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ticker_24hr_stats (
    "time" timestamp without time zone NOT NULL,
    symbol_id integer NOT NULL,
    symbol text NOT NULL,
    pair text,
    price_change numeric(20,10),
    price_change_pct numeric(10,6),
    last_price numeric(20,10) NOT NULL,
    open_price numeric(20,10),
    high_price numeric(20,10),
    low_price numeric(20,10),
    weighted_avg_price numeric(20,10),
    last_quantity numeric(20,10),
    total_volume numeric(30,10),
    total_quote_volume numeric(40,10),
    first_trade_id bigint,
    last_trade_id bigint,
    total_trades integer,
    stats_open_time timestamp without time zone,
    stats_close_time timestamp without time zone,
    inserted_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE ticker_24hr_stats; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.ticker_24hr_stats IS '24hr ticker statistics collected every 1 second';


--
-- Name: COLUMN ticker_24hr_stats."time"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.ticker_24hr_stats."time" IS 'Snapshot time';


--
-- Name: COLUMN ticker_24hr_stats.symbol_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.ticker_24hr_stats.symbol_id IS 'Reference to symbols table';


--
-- Name: COLUMN ticker_24hr_stats.price_change; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.ticker_24hr_stats.price_change IS 'Price change (24hr)';


--
-- Name: COLUMN ticker_24hr_stats.price_change_pct; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.ticker_24hr_stats.price_change_pct IS 'Price change percent (24hr)';


--
-- Name: COLUMN ticker_24hr_stats.last_price; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.ticker_24hr_stats.last_price IS 'Last traded price';


--
-- Name: latest_ticker_stats; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.latest_ticker_stats AS
 SELECT DISTINCT ON (t.symbol_id) s.symbol,
    t."time",
    t.last_price,
    t.open_price,
    t.high_price,
    t.low_price,
    t.total_volume,
    t.total_quote_volume,
    t.price_change,
    t.price_change_pct,
    t.total_trades
   FROM (public.ticker_24hr_stats t
     JOIN public.symbols s ON ((s.id = t.symbol_id)))
  WHERE ((s.is_active = true) AND (s.is_allowed = true))
  ORDER BY t.symbol_id, t."time" DESC;


--
-- Name: pipeline_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_metrics (
    id bigint NOT NULL,
    "timestamp" timestamp without time zone DEFAULT now() NOT NULL,
    symbol_id integer,
    symbol text NOT NULL,
    collection_time_ms integer,
    enrichment_time_ms integer,
    ml_inference_time_ms integer,
    trade_execution_time_ms integer,
    total_time_ms integer NOT NULL,
    active_symbols_count integer,
    active_indicators_count integer,
    status text DEFAULT 'success'::text NOT NULL,
    error_message text,
    inserted_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE pipeline_metrics; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pipeline_metrics IS 'Real-time pipeline performance metrics';


--
-- Name: COLUMN pipeline_metrics.collection_time_ms; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_metrics.collection_time_ms IS 'Time to collect ticker from Binance (ms)';


--
-- Name: COLUMN pipeline_metrics.enrichment_time_ms; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_metrics.enrichment_time_ms IS 'Time to calculate indicators (ms)';


--
-- Name: COLUMN pipeline_metrics.ml_inference_time_ms; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_metrics.ml_inference_time_ms IS 'Time for ML/LLM inference (ms) - future';


--
-- Name: COLUMN pipeline_metrics.trade_execution_time_ms; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_metrics.trade_execution_time_ms IS 'Time to execute trade (ms) - future';


--
-- Name: COLUMN pipeline_metrics.total_time_ms; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_metrics.total_time_ms IS 'Total pipeline time (ms)';


--
-- Name: COLUMN pipeline_metrics.active_symbols_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_metrics.active_symbols_count IS 'Number of active symbols at time of processing';


--
-- Name: COLUMN pipeline_metrics.active_indicators_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_metrics.active_indicators_count IS 'Number of active indicators at time of processing';


--
-- Name: COLUMN pipeline_metrics.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_metrics.status IS 'success (<1000ms), slow (>1000ms), or failed';


--
-- Name: pipeline_metrics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pipeline_metrics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pipeline_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pipeline_metrics_id_seq OWNED BY public.pipeline_metrics.id;


--
-- Name: pipeline_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_state (
    symbol_id integer NOT NULL,
    last_trade_id bigint DEFAULT 0 NOT NULL,
    last_timestamp timestamp without time zone DEFAULT now() NOT NULL,
    is_recovering boolean DEFAULT false NOT NULL,
    recovery_start_time timestamp without time zone,
    recovery_end_time timestamp without time zone,
    trades_processed bigint DEFAULT 0 NOT NULL,
    gaps_detected bigint DEFAULT 0 NOT NULL,
    last_gap_time timestamp without time zone,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE pipeline_state; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pipeline_state IS 'Pipeline state for gap recovery and tracking';


--
-- Name: COLUMN pipeline_state.last_trade_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_state.last_trade_id IS 'Last processed aggregate trade ID';


--
-- Name: COLUMN pipeline_state.is_recovering; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_state.is_recovering IS 'Currently recovering from gap';


--
-- Name: COLUMN pipeline_state.trades_processed; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_state.trades_processed IS 'Total trades processed since start';


--
-- Name: COLUMN pipeline_state.gaps_detected; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_state.gaps_detected IS 'Total gaps detected and recovered';


--
-- Name: recalculation_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recalculation_jobs (
    id bigint NOT NULL,
    indicator_name text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    triggered_by text DEFAULT 'auto'::text NOT NULL,
    ticks_processed bigint DEFAULT 0 NOT NULL,
    total_ticks bigint,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    duration_seconds interval,
    last_error text,
    progress_pct numeric(5,2) DEFAULT 0
);


--
-- Name: TABLE recalculation_jobs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.recalculation_jobs IS 'Background jobs for indicator recalculation';


--
-- Name: recalculation_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.recalculation_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: recalculation_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.recalculation_jobs_id_seq OWNED BY public.recalculation_jobs.id;


--
-- Name: service_status; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_status (
    service_name text NOT NULL,
    status text NOT NULL,
    pid integer,
    host text,
    port integer,
    is_healthy boolean DEFAULT false NOT NULL,
    last_health_check timestamp without time zone,
    health_check_error text,
    uptime_seconds bigint DEFAULT 0,
    records_processed bigint DEFAULT 0,
    errors_last_hour integer DEFAULT 0,
    last_error text,
    last_error_at timestamp without time zone,
    config_version integer DEFAULT 1,
    started_at timestamp without time zone,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb
);


--
-- Name: TABLE service_status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.service_status IS 'Real-time service status';


--
-- Name: symbols_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.symbols_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: symbols_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.symbols_id_seq OWNED BY public.symbols.id;


--
-- Name: system_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_config (
    key text NOT NULL,
    value jsonb NOT NULL,
    description text,
    is_sensitive boolean DEFAULT false NOT NULL,
    is_editable boolean DEFAULT true NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_by text,
    version integer DEFAULT 1 NOT NULL
);


--
-- Name: TABLE system_config; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.system_config IS 'Global system configuration';


--
-- Name: trades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trades (
    trade_id bigint NOT NULL,
    symbol_id integer NOT NULL,
    price numeric(20,10) NOT NULL,
    quantity numeric(20,10) NOT NULL,
    quote_quantity numeric(30,10),
    "time" timestamp without time zone NOT NULL,
    is_buyer_maker boolean,
    inserted_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE trades; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.trades IS 'Individual trade ticks';


--
-- Name: v_active_configuration; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_active_configuration AS
 SELECT ( SELECT count(*) AS count
           FROM public.symbols
          WHERE ((symbols.is_active = true) AND (symbols.is_allowed = true))) AS active_symbols,
    ( SELECT count(*) AS count
           FROM public.indicator_definitions
          WHERE (indicator_definitions.is_active = true)) AS active_indicators,
    ( SELECT array_agg(symbols.symbol ORDER BY symbols.symbol) AS array_agg
           FROM public.symbols
          WHERE ((symbols.is_active = true) AND (symbols.is_allowed = true))) AS symbol_list,
    ( SELECT array_agg(indicator_definitions.name ORDER BY indicator_definitions.name) AS array_agg
           FROM public.indicator_definitions
          WHERE (indicator_definitions.is_active = true)) AS indicator_list,
    ( SELECT count(*) AS count
           FROM public.symbols) AS total_symbols,
    ( SELECT count(*) AS count
           FROM public.indicator_definitions) AS total_indicators;


--
-- Name: VIEW v_active_configuration; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_active_configuration IS 'Current active symbols and indicators configuration';


--
-- Name: v_pipeline_performance; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_pipeline_performance AS
 SELECT date_trunc('minute'::text, pipeline_metrics."timestamp") AS minute,
    count(*) AS ticks_processed,
    round(avg(pipeline_metrics.total_time_ms), 2) AS avg_total_time_ms,
    max(pipeline_metrics.total_time_ms) AS max_total_time_ms,
    round((percentile_cont((0.95)::double precision) WITHIN GROUP (ORDER BY ((pipeline_metrics.total_time_ms)::double precision)))::numeric, 2) AS p95_time_ms,
    round((percentile_cont((0.99)::double precision) WITHIN GROUP (ORDER BY ((pipeline_metrics.total_time_ms)::double precision)))::numeric, 2) AS p99_time_ms,
    round(avg(pipeline_metrics.enrichment_time_ms), 2) AS avg_enrichment_time_ms,
    round(avg(pipeline_metrics.collection_time_ms), 2) AS avg_collection_time_ms,
    round(avg(pipeline_metrics.active_symbols_count), 0) AS avg_active_symbols,
    round(avg(pipeline_metrics.active_indicators_count), 0) AS avg_active_indicators,
    count(*) FILTER (WHERE (pipeline_metrics.total_time_ms > 1000)) AS sla_violations,
    round((((count(*) FILTER (WHERE (pipeline_metrics.total_time_ms > 1000)))::numeric / (count(*))::numeric) * (100)::numeric), 2) AS sla_violation_pct
   FROM public.pipeline_metrics
  WHERE (pipeline_metrics."timestamp" > (now() - '01:00:00'::interval))
  GROUP BY (date_trunc('minute'::text, pipeline_metrics."timestamp"))
  ORDER BY (date_trunc('minute'::text, pipeline_metrics."timestamp")) DESC;


--
-- Name: VIEW v_pipeline_performance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_pipeline_performance IS 'Real-time pipeline performance dashboard (last hour, by minute)';


--
-- Name: v_sla_compliance; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_sla_compliance AS
 SELECT date_trunc('hour'::text, pipeline_metrics."timestamp") AS hour,
    count(*) AS total_ticks,
    count(*) FILTER (WHERE (pipeline_metrics.total_time_ms <= 1000)) AS sla_compliant,
    count(*) FILTER (WHERE (pipeline_metrics.total_time_ms > 1000)) AS sla_violations,
    round((((count(*) FILTER (WHERE (pipeline_metrics.total_time_ms <= 1000)))::numeric / (count(*))::numeric) * (100)::numeric), 2) AS compliance_pct,
    round(avg(pipeline_metrics.total_time_ms), 2) AS avg_time_ms,
    max(pipeline_metrics.total_time_ms) AS max_time_ms,
    round((percentile_cont((0.95)::double precision) WITHIN GROUP (ORDER BY ((pipeline_metrics.total_time_ms)::double precision)))::numeric, 2) AS p95_time_ms,
    round((percentile_cont((0.99)::double precision) WITHIN GROUP (ORDER BY ((pipeline_metrics.total_time_ms)::double precision)))::numeric, 2) AS p99_time_ms
   FROM public.pipeline_metrics
  WHERE (pipeline_metrics."timestamp" > (now() - '24:00:00'::interval))
  GROUP BY (date_trunc('hour'::text, pipeline_metrics."timestamp"))
  ORDER BY (date_trunc('hour'::text, pipeline_metrics."timestamp")) DESC;


--
-- Name: VIEW v_sla_compliance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_sla_compliance IS 'SLA compliance report (1-second target, last 24 hours)';


--
-- Name: v_slowest_symbols; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_slowest_symbols AS
 SELECT s.symbol,
    s.is_active,
    count(*) AS ticks_processed,
    round(avg(pm.total_time_ms), 2) AS avg_time_ms,
    max(pm.total_time_ms) AS max_time_ms,
    round((percentile_cont((0.95)::double precision) WITHIN GROUP (ORDER BY ((pm.total_time_ms)::double precision)))::numeric, 2) AS p95_time_ms,
    count(*) FILTER (WHERE (pm.total_time_ms > 1000)) AS sla_violations,
    round(avg(pm.enrichment_time_ms), 2) AS avg_enrichment_ms,
    round(avg(pm.active_indicators_count), 0) AS avg_indicators
   FROM (public.pipeline_metrics pm
     JOIN public.symbols s ON ((s.id = pm.symbol_id)))
  WHERE (pm."timestamp" > (now() - '01:00:00'::interval))
  GROUP BY s.symbol, s.is_active
  ORDER BY (round(avg(pm.total_time_ms), 2)) DESC
 LIMIT 20;


--
-- Name: VIEW v_slowest_symbols; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_slowest_symbols IS 'Top 20 slowest symbols for capacity planning (last hour)';


--
-- Name: wide_vectors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wide_vectors (
    "time" timestamp with time zone NOT NULL,
    vector jsonb NOT NULL,
    column_names text[] NOT NULL,
    symbols text[] NOT NULL,
    vector_size integer NOT NULL,
    symbol_count integer NOT NULL,
    indicator_count integer NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: config_change_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.config_change_log ALTER COLUMN id SET DEFAULT nextval('public.config_change_log_id_seq'::regclass);


--
-- Name: data_quality_issues id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_issues ALTER COLUMN id SET DEFAULT nextval('public.data_quality_issues_id_seq'::regclass);


--
-- Name: data_quality_metrics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_metrics ALTER COLUMN id SET DEFAULT nextval('public.data_quality_metrics_id_seq'::regclass);


--
-- Name: indicator_definitions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicator_definitions ALTER COLUMN id SET DEFAULT nextval('public.indicator_definitions_id_seq'::regclass);


--
-- Name: pipeline_metrics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_metrics ALTER COLUMN id SET DEFAULT nextval('public.pipeline_metrics_id_seq'::regclass);


--
-- Name: recalculation_jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recalculation_jobs ALTER COLUMN id SET DEFAULT nextval('public.recalculation_jobs_id_seq'::regclass);


--
-- Name: symbols id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.symbols ALTER COLUMN id SET DEFAULT nextval('public.symbols_id_seq'::regclass);


--
-- Name: candles_1s candles_1s_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candles_1s
    ADD CONSTRAINT candles_1s_pkey PRIMARY KEY ("time", symbol_id);


--
-- Name: collection_config collection_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_config
    ADD CONSTRAINT collection_config_pkey PRIMARY KEY (symbol_id);


--
-- Name: config_change_log config_change_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.config_change_log
    ADD CONSTRAINT config_change_log_pkey PRIMARY KEY (id);


--
-- Name: data_quality_issues data_quality_issues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_issues
    ADD CONSTRAINT data_quality_issues_pkey PRIMARY KEY (id);


--
-- Name: data_quality_metrics data_quality_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_metrics
    ADD CONSTRAINT data_quality_metrics_pkey PRIMARY KEY (id);


--
-- Name: data_quality_metrics data_quality_metrics_symbol_id_date_hour_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_metrics
    ADD CONSTRAINT data_quality_metrics_symbol_id_date_hour_key UNIQUE (symbol_id, date, hour);


--
-- Name: indicator_definitions indicator_definitions_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicator_definitions
    ADD CONSTRAINT indicator_definitions_name_key UNIQUE (name);


--
-- Name: indicator_definitions indicator_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicator_definitions
    ADD CONSTRAINT indicator_definitions_pkey PRIMARY KEY (id);


--
-- Name: pipeline_metrics pipeline_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_metrics
    ADD CONSTRAINT pipeline_metrics_pkey PRIMARY KEY (id);


--
-- Name: pipeline_state pipeline_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_state
    ADD CONSTRAINT pipeline_state_pkey PRIMARY KEY (symbol_id);


--
-- Name: recalculation_jobs recalculation_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recalculation_jobs
    ADD CONSTRAINT recalculation_jobs_pkey PRIMARY KEY (id);


--
-- Name: service_status service_status_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_status
    ADD CONSTRAINT service_status_pkey PRIMARY KEY (service_name);


--
-- Name: symbols symbols_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.symbols
    ADD CONSTRAINT symbols_pkey PRIMARY KEY (id);


--
-- Name: symbols symbols_symbol_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.symbols
    ADD CONSTRAINT symbols_symbol_key UNIQUE (symbol);


--
-- Name: system_config system_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_config
    ADD CONSTRAINT system_config_pkey PRIMARY KEY (key);


--
-- Name: candle_indicators tick_indicators_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candle_indicators
    ADD CONSTRAINT tick_indicators_pkey PRIMARY KEY ("time", symbol_id);


--
-- Name: ticker_24hr_stats ticker_24hr_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticker_24hr_stats
    ADD CONSTRAINT ticker_24hr_stats_pkey PRIMARY KEY ("time", symbol_id);


--
-- Name: trades trades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT trades_pkey PRIMARY KEY (trade_id, symbol_id);


--
-- Name: wide_vectors wide_vectors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wide_vectors
    ADD CONSTRAINT wide_vectors_pkey PRIMARY KEY ("time");


--
-- Name: idx_candle_indicators_keys; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candle_indicators_keys ON public.candle_indicators USING gin (indicator_keys);


--
-- Name: idx_candle_indicators_symbol_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candle_indicators_symbol_time ON public.candle_indicators USING btree (symbol_id, "time" DESC);


--
-- Name: idx_candle_indicators_time_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candle_indicators_time_symbol ON public.candle_indicators USING btree ("time" DESC, symbol_id);


--
-- Name: idx_candle_indicators_values; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candle_indicators_values ON public.candle_indicators USING gin ("values");


--
-- Name: idx_candles_1s_not_processed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candles_1s_not_processed ON public.candles_1s USING btree ("time") WHERE (processed = false);


--
-- Name: idx_collection_config_collecting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_collection_config_collecting ON public.collection_config USING btree (is_collecting) WHERE (is_collecting = true);


--
-- Name: idx_config_change_log_changed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_config_change_log_changed_at ON public.config_change_log USING btree (changed_at DESC);


--
-- Name: idx_config_change_log_type_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_config_change_log_type_key ON public.config_change_log USING btree (config_type, config_key);


--
-- Name: idx_indicator_definitions_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_indicator_definitions_active ON public.indicator_definitions USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_indicator_definitions_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_indicator_definitions_category ON public.indicator_definitions USING btree (category);


--
-- Name: idx_pipeline_metrics_sla; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_metrics_sla ON public.pipeline_metrics USING btree (total_time_ms DESC) WHERE (total_time_ms > 1000);


--
-- Name: idx_pipeline_metrics_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_metrics_status ON public.pipeline_metrics USING btree (status);


--
-- Name: idx_pipeline_metrics_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_metrics_symbol ON public.pipeline_metrics USING btree (symbol_id);


--
-- Name: idx_pipeline_metrics_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_metrics_time ON public.pipeline_metrics USING btree ("timestamp" DESC);


--
-- Name: idx_pipeline_metrics_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_metrics_timestamp ON public.pipeline_metrics USING btree ("timestamp" DESC);


--
-- Name: idx_pipeline_state_recovering; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pipeline_state_recovering ON public.pipeline_state USING btree (is_recovering) WHERE (is_recovering = true);


--
-- Name: idx_quality_issues_detected_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quality_issues_detected_at ON public.data_quality_issues USING btree (detected_at DESC);


--
-- Name: idx_quality_issues_resolved; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quality_issues_resolved ON public.data_quality_issues USING btree (resolved) WHERE (resolved = false);


--
-- Name: idx_quality_issues_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quality_issues_symbol ON public.data_quality_issues USING btree (symbol_id);


--
-- Name: idx_quality_issues_unresolved; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quality_issues_unresolved ON public.data_quality_issues USING btree (resolved) WHERE (resolved = false);


--
-- Name: idx_quality_metrics_symbol_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quality_metrics_symbol_date ON public.data_quality_metrics USING btree (symbol_id, date DESC);


--
-- Name: idx_recalculation_jobs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_recalculation_jobs_created_at ON public.recalculation_jobs USING btree (created_at DESC);


--
-- Name: idx_recalculation_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_recalculation_jobs_status ON public.recalculation_jobs USING btree (status);


--
-- Name: idx_symbols_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_symbols_active ON public.symbols USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_symbols_allowed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_symbols_allowed ON public.symbols USING btree (is_allowed) WHERE (is_allowed = true);


--
-- Name: idx_symbols_is_test; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_symbols_is_test ON public.symbols USING btree (is_test);


--
-- Name: idx_symbols_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_symbols_status ON public.symbols USING btree (status);


--
-- Name: idx_symbols_test; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_symbols_test ON public.symbols USING btree (is_test);


--
-- Name: idx_system_config_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_system_config_key ON public.system_config USING btree (key);


--
-- Name: idx_ticker_stats_symbol_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ticker_stats_symbol_time ON public.ticker_24hr_stats USING btree (symbol_id, "time" DESC);


--
-- Name: idx_ticker_stats_time_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ticker_stats_time_symbol ON public.ticker_24hr_stats USING btree ("time" DESC, symbol_id);


--
-- Name: idx_ticker_symbol_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ticker_symbol_time ON public.ticker_24hr_stats USING btree (symbol_id, "time" DESC);


--
-- Name: idx_ticker_time_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ticker_time_symbol ON public.ticker_24hr_stats USING btree ("time" DESC, symbol_id);


--
-- Name: idx_trades_symbol_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trades_symbol_time ON public.trades USING btree (symbol_id, "time" DESC);


--
-- Name: idx_trades_time_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trades_time_symbol ON public.trades USING btree ("time" DESC, symbol_id);


--
-- Name: idx_trades_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_trades_unique ON public.trades USING btree (trade_id, symbol_id);


--
-- Name: indicator_definitions indicator_definitions_change_notification; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER indicator_definitions_change_notification AFTER INSERT OR DELETE OR UPDATE ON public.indicator_definitions FOR EACH ROW EXECUTE FUNCTION public.notify_indicator_change();


--
-- Name: system_config system_config_change_notification; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER system_config_change_notification AFTER UPDATE ON public.system_config FOR EACH ROW WHEN ((old.value IS DISTINCT FROM new.value)) EXECUTE FUNCTION public.notify_config_change();


--
-- Name: system_config system_config_change_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER system_config_change_trigger AFTER UPDATE ON public.system_config FOR EACH ROW EXECUTE FUNCTION public.notify_config_change();


--
-- Name: candle_indicators update_candle_indicators_timestamp; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_candle_indicators_timestamp BEFORE UPDATE ON public.candle_indicators FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: collection_config update_collection_config_timestamp; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_collection_config_timestamp BEFORE UPDATE ON public.collection_config FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: indicator_definitions update_indicator_definitions_timestamp; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_indicator_definitions_timestamp BEFORE UPDATE ON public.indicator_definitions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: pipeline_state update_pipeline_state_timestamp_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_pipeline_state_timestamp_trigger BEFORE UPDATE ON public.pipeline_state FOR EACH ROW EXECUTE FUNCTION public.update_pipeline_state_timestamp();


--
-- Name: service_status update_service_status_timestamp; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_service_status_timestamp BEFORE UPDATE ON public.service_status FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: symbols update_symbols_timestamp; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_symbols_timestamp BEFORE UPDATE ON public.symbols FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: system_config update_system_config_timestamp; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_system_config_timestamp BEFORE UPDATE ON public.system_config FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: candles_1s candles_1s_symbol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candles_1s
    ADD CONSTRAINT candles_1s_symbol_id_fkey FOREIGN KEY (symbol_id) REFERENCES public.symbols(id);


--
-- Name: collection_config collection_config_symbol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_config
    ADD CONSTRAINT collection_config_symbol_id_fkey FOREIGN KEY (symbol_id) REFERENCES public.symbols(id) ON DELETE CASCADE;


--
-- Name: data_quality_issues data_quality_issues_symbol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_issues
    ADD CONSTRAINT data_quality_issues_symbol_id_fkey FOREIGN KEY (symbol_id) REFERENCES public.symbols(id);


--
-- Name: data_quality_metrics data_quality_metrics_symbol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_metrics
    ADD CONSTRAINT data_quality_metrics_symbol_id_fkey FOREIGN KEY (symbol_id) REFERENCES public.symbols(id);


--
-- Name: pipeline_metrics pipeline_metrics_symbol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_metrics
    ADD CONSTRAINT pipeline_metrics_symbol_id_fkey FOREIGN KEY (symbol_id) REFERENCES public.symbols(id);


--
-- Name: pipeline_state pipeline_state_symbol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_state
    ADD CONSTRAINT pipeline_state_symbol_id_fkey FOREIGN KEY (symbol_id) REFERENCES public.symbols(id) ON DELETE CASCADE;


--
-- Name: recalculation_jobs recalculation_jobs_indicator_name_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recalculation_jobs
    ADD CONSTRAINT recalculation_jobs_indicator_name_fkey FOREIGN KEY (indicator_name) REFERENCES public.indicator_definitions(name);


--
-- Name: candle_indicators tick_indicators_symbol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candle_indicators
    ADD CONSTRAINT tick_indicators_symbol_id_fkey FOREIGN KEY (symbol_id) REFERENCES public.symbols(id);


--
-- Name: ticker_24hr_stats ticker_24hr_stats_symbol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticker_24hr_stats
    ADD CONSTRAINT ticker_24hr_stats_symbol_id_fkey FOREIGN KEY (symbol_id) REFERENCES public.symbols(id);


--
-- Name: trades trades_symbol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT trades_symbol_id_fkey FOREIGN KEY (symbol_id) REFERENCES public.symbols(id);


--
-- PostgreSQL database dump complete
--

\unrestrict kk2Mqcjqi3tJr9k9v3li1gQn5q9BQsy9wMSFzckzbSJcbWfl4MToK62y9XrNq4G

