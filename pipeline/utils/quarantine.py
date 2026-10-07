"""
pipeline/utils/quarantine.py

Phase 1 / Task 5 (ADR-0001) — shared quarantine writer used by all three
domain parsers (NDMA, PDMA, PMD). See CLAUDE.md rule 6: every rejection
must land in dq.quarantine with a source document reference, the raw
payload, a machine-readable reason code, a human-readable message, the
parser version, and a timestamp.

A quarantine write must never itself abort the parse it is recording a
rejection for — if dq.quarantine doesn't exist yet, or the DB is
unreachable, this logs the failure and returns False rather than
raising. The caller's own reject-counting (used for the rejection-ratio
gate) is independent of whether the DB write succeeds.
"""

import json
import logging

from sqlalchemy import text

from config.database import engine

logger = logging.getLogger(__name__)


def write_quarantine(
    source,
    domain,
    source_document,
    reason_code,
    message,
    parser_version,
    raw_payload=None,
):
    """
    Insert one rejection record into dq.quarantine.

    source           : 'ndma' | 'pdma' | 'pmd'
    domain           : e.g. 'sitrep' | 'daily' | 'rainfall' | 'gauge'
                        | 'daily_forecast' | 'weekly_outlook'
    source_document  : filename/path the record came from
    reason_code      : machine-readable, e.g. 'schema_invalid',
                        'quality_below_threshold', 'unhandled_exception',
                        'row_too_short', 'failed_weather_validation'
    message          : human-readable detail
    parser_version   : module-level version string of the calling parser
    raw_payload      : the offending row/record as a JSON-serialisable
                        value, where available. For whole-file
                        rejections (e.g. NDMA PDFs already copied to
                        data/rejected/<source>/) pass None — source_document
                        is the on-disk reference.

    Returns True when the rejection is recorded (including: an identical OPEN rejection already exists, so nothing new is inserted),
    False if the write itself failed (logged, never raised).
    """

    try:

        payload_json = (
            json.dumps(raw_payload, ensure_ascii=False, default=str)
            if raw_payload is not None
            else None
        )

        with engine.begin() as conn:

            conn.execute(
                text(
                    """
                    INSERT INTO dq.quarantine (
                        source,
                        domain,
                        source_document,
                        raw_payload,
                        reason_code,
                        message,
                        parser_version
                    )
                    SELECT
                        :source,
                        :domain,
                        :source_document,
                        CAST(:raw_payload AS JSONB),
                        :reason_code,
                        :message,
                        :parser_version
                    -- Task 40: idempotent. A scheduled parser re-reads every file on every run, so the SAME rejection must not be
                    -- recorded again while it is still open (it stays countable, queryable and re-processable exactly once).
                    WHERE NOT EXISTS (
                        SELECT 1 FROM dq.quarantine q
                        WHERE q.source = :source
                          AND q.domain IS NOT DISTINCT FROM :domain
                          AND q.source_document = :source_document
                          AND q.reason_code = :reason_code
                          AND q.parser_version = :parser_version
                          AND q.status = 'open'
                          AND q.raw_payload IS NOT DISTINCT FROM CAST(:raw_payload AS JSONB)
                    )
                    """
                ),
                {
                    "source": source,
                    "domain": domain,
                    "source_document": source_document,
                    "raw_payload": payload_json,
                    "reason_code": reason_code,
                    "message": message,
                    "parser_version": parser_version,
                },
            )

        return True

    except Exception as e:

        logger.error(
            "QUARANTINE WRITE FAILED | source=%s domain=%s document=%s reason=%s | %s",
            source,
            domain,
            source_document,
            reason_code,
            e,
        )

        return False
