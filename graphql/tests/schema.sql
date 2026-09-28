-- The tables this service reads, copied from
-- o1-labs/uptime-service-validation uptime_service_validation/database/create_tables.sql
-- (columns this service does not read are left out).
CREATE TABLE bot_logs (
    id SERIAL PRIMARY KEY,
    files_processed INT,
    batch_start_epoch BIGINT,
    batch_end_epoch BIGINT
);

CREATE TABLE nodes (
    id SERIAL PRIMARY KEY,
    block_producer_key TEXT,
    updated_at TIMESTAMPTZ(6),
    score INT,
    score_percent NUMERIC(5,2),
    application_status BOOLEAN
);

CREATE TABLE points (
    id SERIAL PRIMARY KEY,
    node_id INT REFERENCES nodes(id),
    bot_log_id INT REFERENCES bot_logs(id)
);

CREATE TABLE points_summary (
    bot_log_id INT NOT NULL,
    node_id INT NOT NULL
);
CREATE UNIQUE INDEX uq_ps_bot_log_node ON points_summary USING btree (bot_log_id, node_id);

CREATE OR REPLACE FUNCTION fn_update_point_summary()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO points_summary(bot_log_id, node_id)
    VALUES(NEW.bot_log_id, NEW.node_id)
    ON CONFLICT (bot_log_id, node_id) DO NOTHING;
    RETURN new;
END;
$$;

CREATE TRIGGER trg_after_insert_points
AFTER INSERT ON points
FOR EACH ROW EXECUTE FUNCTION fn_update_point_summary();

CREATE TABLE submissions (
    id SERIAL PRIMARY KEY,
    submitted_at_date DATE NOT NULL,
    submitted_at TIMESTAMP NOT NULL,
    submitter TEXT NOT NULL
);
CREATE INDEX idx_submissions_submitter_datetime ON submissions (submitter, submitted_at DESC);
