"""Printable CareCredits affiliation certificates (CERT-01 / DEC-10)."""
from __future__ import annotations

import hashlib
import html
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from digest import progress_snapshot
from portal_models import Account, AffiliationCertificate


TZ = ZoneInfo('Asia/Kuala_Lumpur')
DISCLAIMER_VERSION = 'CERT-01-v1'
DISCLAIMER = (
    'This document confirms CareCredits affiliation and summarises self-reported CPD activity '
    'recorded in CareCredits. It is not an MMC, MOH, or APC compliance certificate and does not '
    'replace regulator-issued evidence.'
)


def issue_certificate(db: Session, account: Account, year: int) -> AffiliationCertificate:
    if not 1900 <= year <= 2200:
        raise ValueError('Invalid year.')
    progress = progress_snapshot(db, account.id, year)
    issued_at = time.time()
    material = '|'.join([
        account.id,
        str(year),
        str(progress['points']),
        DISCLAIMER_VERSION,
        f'{issued_at:.6f}',
    ])
    document_hash = hashlib.sha256(material.encode()).hexdigest()
    row = AffiliationCertificate(
        account_id=account.id,
        year=year,
        recorded_points_snapshot=float(progress['points']),
        issued_at=issued_at,
        document_hash=document_hash,
        disclaimer_version=DISCLAIMER_VERSION,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def certificate_json(row: AffiliationCertificate) -> dict:
    return {
        'id': row.id,
        'year': row.year,
        'recorded_points_snapshot': row.recorded_points_snapshot,
        'issued_at': row.issued_at,
        'document_hash': row.document_hash,
        'disclaimer_version': row.disclaimer_version,
        'download_path': f'/api/v1/me/certificates/{row.id}',
    }


def render_html(account: Account, row: AffiliationCertificate) -> str:
    issued = datetime.fromtimestamp(row.issued_at, TZ).strftime('%d %B %Y, %H:%M %Z')
    name = html.escape(account.name)
    email = html.escape(account.email)
    city = html.escape(account.city or '')
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>CareCredits affiliation certificate — {row.year}</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  body {{
    font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
    color: #10233f;
    background: linear-gradient(180deg, #f3f7fc 0%, #ffffff 40%);
    margin: 0;
    padding: 32px;
  }}
  .sheet {{
    max-width: 720px;
    margin: 0 auto;
    border: 1px solid #c5d4e8;
    padding: 48px 40px;
    background: #fff;
  }}
  .brand {{
    font-size: 28px;
    letter-spacing: 0.04em;
    font-weight: 700;
    color: #0b4f9c;
  }}
  h1 {{
    font-size: 22px;
    margin: 28px 0 8px;
    font-weight: 600;
  }}
  .meta {{ margin: 0 0 24px; color: #4a607a; font-size: 14px; }}
  .points {{
    font-size: 42px;
    font-weight: 700;
    color: #0b4f9c;
    margin: 8px 0;
  }}
  .label {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; color: #6b7f96; }}
  .disclaimer {{
    margin-top: 36px;
    padding-top: 16px;
    border-top: 1px solid #d7e2ef;
    font-size: 12px;
    line-height: 1.5;
    color: #5a6f86;
  }}
  .hash {{ font-family: ui-monospace, Menlo, monospace; font-size: 11px; word-break: break-all; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .sheet {{ border: none; }}
    .noprint {{ display: none; }}
  }}
</style>
</head>
<body>
  <div class="sheet">
    <div class="brand">CareCredits</div>
    <p class="meta">Malaysia GP CPD tracking · affiliation record</p>
    <h1>Affiliation certificate</h1>
    <p>This certifies that <strong>{name}</strong> ({email}) is affiliated with CareCredits
       for the calendar year <strong>{row.year}</strong>{f' · {city}' if city else ''}.</p>
    <p class="label">Self-reported CPD points recorded in CareCredits</p>
    <p class="points">{row.recorded_points_snapshot:g}</p>
    <p class="meta">Issued {issued}</p>
    <p class="disclaimer">{html.escape(DISCLAIMER)}</p>
    <p class="disclaimer hash">Document hash: {html.escape(row.document_hash)} · {html.escape(row.disclaimer_version)}</p>
    <p class="noprint meta"><button onclick="window.print()">Print / Save as PDF</button></p>
  </div>
</body>
</html>
"""
