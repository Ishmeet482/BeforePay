-- Optional OWNER operation; never run during startup, build or migrations.
-- Connect privately to the verified dedicated demo database before applying.
BEGIN;
DO $$ BEGIN
  IF current_database() <> 'beforepay_demo_2026'
     OR current_user <> 'neondb_owner' THEN
    RAISE EXCEPTION 'Wrong dedicated database or migration owner';
  END IF;
END $$;
GRANT INSERT ON public.payment_attempts, public.payment_events,
  public.sandbox_receipts TO beforepay_demo_runtime;
GRANT UPDATE (order_id, capture_id, status, error_code,
  capture_requested_at, updated_at) ON public.payment_attempts
  TO beforepay_demo_runtime;
-- No UPDATE on immutable history/bindings, DELETE, TRUNCATE, ownership,
-- schema/function privileges, or webhook recording privileges are added.
COMMIT;
