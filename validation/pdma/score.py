"""
PDMA Quality Score

Production Version

Overall Quality Score

Schema Validation : 60%
Completeness      : 40%
"""

from datetime import datetime

from validation.pdma.schema import validate_schema
from validation.pdma.completeness import completeness_score


# ==========================================================
# QUALITY SCORE
# ==========================================================

def quality_score(report):

    # ------------------------------------------------------
    # Schema Validation
    # ------------------------------------------------------

    schema_valid, schema_errors = validate_schema(report)

    schema_score = 100 if schema_valid else 0

    # ------------------------------------------------------
    # Completeness
    # ------------------------------------------------------

    completeness = completeness_score(report)

    completeness_value = completeness["score"]

    # ------------------------------------------------------
    # Final Score
    # ------------------------------------------------------

    final_score = round(
        (schema_score * 0.60)
        + (completeness_value * 0.40),
        2,
    )

    # ------------------------------------------------------
    # Grade
    # ------------------------------------------------------

    if final_score >= 90:
        status = "Excellent"

    elif final_score >= 75:
        status = "Good"

    elif final_score >= 60:
        status = "Acceptable"

    else:
        status = "Rejected"

    # ------------------------------------------------------
    # Result
    # ------------------------------------------------------

    return {

        "schema_valid": schema_valid,

        "schema_score": schema_score,

        "schema_errors": schema_errors,

        "completeness_score": completeness_value,

        # Existing key
        "quality_score": final_score,

        # Backward compatibility
        "score": final_score,

        "status": status,

        "validated_at": datetime.utcnow().isoformat()

    }