"""Task 19 -- Tier-1 national dataset parsers (SUPARCO, EPA Punjab AQI, FFC, PMD/NDMC).

Every parser is a pure function over raw bytes/paths acquired by Task 15. Raw files and
manifests are only ever read, never written.
"""

PARSER_VERSION = "tier1-parser-1.0.0"
