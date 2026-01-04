from sqlalchemy import Column, String, DateTime, Enum, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
import enum
from uuid6 import uuid7

Base = declarative_base()

# Enums
class WorkflowTypeEnum(str, enum.Enum):
    WEB_QUERY = "WEB_QUERY"
    WEB_ACTION = "WEB_ACTION"
    REASON = "REASON"

class JobStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"

# Job Entity
class Job(Base):
    __tablename__ = "jobs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)      
    workflow_id = Column(PG_UUID(as_uuid=True), nullable=False, default=uuid7)
    node_id = Column(String, nullable=False, default="root")                
    goal = Column(String, nullable=False)                                   
    workflow_type = Column(Enum(WorkflowTypeEnum), nullable=False)
    status = Column(Enum(JobStatusEnum), nullable=False, default=JobStatusEnum.PENDING)
    result = Column(String)                                                
    error_message = Column(String)                                         
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class JobLog(Base):
    __tablename__ = "job_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)     
    job_id = Column(PG_UUID(as_uuid=True), nullable=False, default=uuid7) 
    event_type = Column(Enum(JobStatusEnum), nullable=False, default=JobStatusEnum.PENDING)
