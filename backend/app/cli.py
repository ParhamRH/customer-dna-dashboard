"""Operations CLI:  python -m app.cli <command>

  migrate                     apply database migrations (owner role)
  create-admin                create or promote a platform super administrator
  seed-demo                   create three fictional DEMO customers (development only)
  worker                      run the background job worker
  drain                       run every queued job inline, then exit (dev / small installs)
  cleanup                     expire old exports, remove abandoned import staging files
  reindex                     regenerate embeddings of one brand (after changing the embedding model)
  check                       verify configuration, database roles, RLS and media tooling
"""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _alembic_cfg():
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


def cmd_migrate(args: argparse.Namespace) -> int:
    from alembic import command

    command.upgrade(_alembic_cfg(), args.revision)
    print(f"database migrated to {args.revision}")
    return 0


def _password(args: argparse.Namespace, env: str) -> str:
    pw = args.password or os.environ.get(env)
    if not pw:
        if not sys.stdin.isatty():
            raise SystemExit(f"provide --password or set {env}")
        pw = getpass.getpass("Password (min 10 chars): ")
    return pw


def cmd_create_admin(args: argparse.Namespace) -> int:
    from app.services.accounts import create_platform_admin

    uid = create_platform_admin(args.email, args.name, _password(args, "BDNA_ADMIN_PASSWORD"))
    print(f"platform administrator ready: {args.email} ({uid})")
    return 0


def cmd_seed_demo(args: argparse.Namespace) -> int:
    from app.config import get_settings

    if get_settings().is_production and not args.force:
        raise SystemExit("refusing to seed DEMO data in production (use --force if you really mean it)")
    from app.seed.demo import DEMO_PASSWORD, seed

    pw = args.admin_password or os.environ.get("BDNA_ADMIN_PASSWORD") or "admin-password-2026"
    out = seed(args.admin_email, pw, process_jobs=not args.no_process)
    print(json.dumps({**out, "demo_user_password": DEMO_PASSWORD, "platform_admin_password": pw,
                      "note": "DEMO DATA — fictional customers for development only"}, indent=2))
    return 0


def cmd_worker(_: argparse.Namespace) -> int:
    from app.jobs.worker import main

    main()
    return 0


def cmd_drain(args: argparse.Namespace) -> int:
    from app.jobs.queue import drain

    n = drain(max_jobs=args.max)
    print(f"ran {n} job(s)")
    return 0


def cmd_cleanup(_: argparse.Namespace) -> int:
    from app.services.maintenance import run_all

    print(json.dumps(run_all()))
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    import uuid

    from sqlalchemy import select

    from app.db.session import TenantContext, system_session, tenant_session
    from app.jobs.queue import enqueue
    from app.models import Brand, Organization

    with system_session() as s:
        org = s.scalar(select(Organization).where((Organization.slug == args.org) | (Organization.id == _maybe_uuid(args.org))))
        if org is None:
            raise SystemExit(f"organization {args.org!r} not found")
        org_id = org.id
    with tenant_session(TenantContext(org_id=org_id)) as db:
        brands = db.scalars(select(Brand)).all()
        targets = [b for b in brands if not args.brand or args.brand in (b.slug, str(b.id))]
        if not targets:
            raise SystemExit("no matching brand")
        for b in targets:
            enqueue(db, org_id, "brand.reindex", brand_id=b.id, entity_type="brand", entity_id=b.id, priority=90)
            print(f"queued reindex for {org.slug}/{b.slug}")
    _ = uuid
    return 0


def _maybe_uuid(v: str):
    import uuid

    try:
        return uuid.UUID(v)
    except ValueError:
        return uuid.UUID(int=0)


def cmd_check(_: argparse.Namespace) -> int:
    """Fail-fast deployment check. Exit code 1 if anything critical is wrong."""
    from sqlalchemy import text

    from app.config import get_settings
    from app.db.session import TenantContext, system_session, tenant_session

    s = get_settings()
    ok = True

    def line(status: str, msg: str) -> None:
        print(f"[{status:>4}] {msg}")

    try:
        with system_session() as db:
            db.execute(text("SELECT 1"))
            ver = db.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            rev = db.scalar(text("SELECT version_num FROM alembic_version"))
            forced = db.scalar(text("SELECT count(*) FROM pg_class WHERE relrowsecurity AND relforcerowsecurity AND relkind='r'"))
            bypass = db.scalar(text("SELECT rolbypassrls FROM pg_roles WHERE rolname = :r"), {"r": s.db_app_role})
        line("ok", f"database reachable; migration {rev}; pgvector {ver}; {forced} tables with FORCED row level security")
        if bypass:
            ok = False
            line("FAIL", f"runtime role {s.db_app_role} has BYPASSRLS — tenant isolation would be disabled")
        else:
            line("ok", f"runtime role {s.db_app_role} cannot bypass RLS")
        with tenant_session(TenantContext(org_id=None)) as db:
            visible = db.scalar(text("SELECT count(*) FROM brands"))
        if visible:
            ok = False
            line("FAIL", f"{visible} brand rows visible without a tenant context")
        else:
            line("ok", "no tenant rows are visible without a tenant context (fails closed)")
    except Exception as e:  # noqa: BLE001
        ok = False
        line("FAIL", f"database: {e}")
    for tool in (s.ffmpeg_binary, s.ffprobe_binary, s.tesseract_binary):
        line("ok" if shutil.which(tool) else "warn", f"{tool} {'found' if shutil.which(tool) else 'missing'}")
    if s.is_production:
        for cond, msg in ((s.secret_key.startswith("dev-insecure"), "BDNA_SECRET_KEY is the development default"),
                          (not s.encryption_key, "BDNA_ENCRYPTION_KEY not set"),
                          (not s.cookie_secure, "BDNA_COOKIE_SECURE should be true behind HTTPS"),
                          (s.storage_backend == "local", "local storage in production")):
            if cond:
                line("warn", msg)
    from app.ai import registry

    for cap, info in registry.describe().items():
        line("warn" if info["development_adapter"] else "ok",
             f"AI {cap}: {info['provider']} {info.get('model') or ''}" + (" (DEVELOPMENT ADAPTER)" if info["development_adapter"] else ""))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.environ.get("BDNA_LOG_LEVEL", "WARNING"), format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("migrate")
    p.add_argument("--revision", default="head")
    p.set_defaults(fn=cmd_migrate)
    p = sub.add_parser("create-admin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Platform Administrator")
    p.add_argument("--password", help="or set BDNA_ADMIN_PASSWORD")
    p.set_defaults(fn=cmd_create_admin)
    p = sub.add_parser("seed-demo")
    p.add_argument("--admin-email", default=os.environ.get("BDNA_ADMIN_EMAIL", "admin@platform.local"))
    p.add_argument("--admin-password")
    p.add_argument("--no-process", action="store_true", help="do not run processing jobs inline")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_seed_demo)
    sub.add_parser("worker").set_defaults(fn=cmd_worker)
    p = sub.add_parser("drain")
    p.add_argument("--max", type=int, default=10000)
    p.set_defaults(fn=cmd_drain)
    sub.add_parser("cleanup").set_defaults(fn=cmd_cleanup)
    p = sub.add_parser("reindex")
    p.add_argument("--org", required=True, help="organization slug or id")
    p.add_argument("--brand", help="brand slug or id (default: all brands)")
    p.set_defaults(fn=cmd_reindex)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
