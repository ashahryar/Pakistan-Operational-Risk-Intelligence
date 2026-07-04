from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    Date,
    DateTime,
    Text,
)

from sqlalchemy.orm import declarative_base

Base = declarative_base()


class PDMAReport(Base):
    __tablename__ = "pdma_reports"

    id = Column(Integer, primary_key=True)

    source = Column(String(20))
    report_type = Column(String(50))

    report_date = Column(Date)

    district = Column(String(100))
    station = Column(String(100))

    rainfall_mm = Column(Float)

    river = Column(String(100))
    water_level = Column(Float)

    summary = Column(Text)

    pdf_name = Column(String(255))

    created_at = Column(DateTime)