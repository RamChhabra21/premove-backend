"""
Custom exception hierarchy for the Premove Backend.

This module defines all custom exceptions used throughout the application
for better error handling and debugging.
"""

from typing import Optional, Any


class PremoveBaseException(Exception):
    """Base exception for all Premove-specific errors."""
    
    def __init__(self, message: str, details: Optional[Any] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)


# Job-related exceptions
class JobException(PremoveBaseException):
    """Base exception for job-related errors."""
    pass


class JobNotFoundException(JobException):
    """Raised when a job is not found in the database."""
    
    def __init__(self, job_id: str):
        super().__init__(
            message=f"Job with ID {job_id} not found",
            details={"job_id": job_id}
        )


class JobCreationException(JobException):
    """Raised when job creation fails."""
    pass


class JobUpdateException(JobException):
    """Raised when job update fails."""
    pass


# Web Automation exceptions
class WebAutomationException(PremoveBaseException):
    """Base exception for web automation errors."""
    pass


class WebAutomationNotFoundException(WebAutomationException):
    """Raised when a web automation is not found."""
    
    def __init__(self, automation_id: Optional[str] = None, workflow_id: Optional[str] = None, node_id: Optional[str] = None):
        if automation_id:
            message = f"Web automation with ID {automation_id} not found"
            details = {"automation_id": automation_id}
        else:
            message = f"Web automation for workflow {workflow_id}, node {node_id} not found"
            details = {"workflow_id": workflow_id, "node_id": node_id}
        super().__init__(message=message, details=details)


class WebAutomationDuplicateException(WebAutomationException):
    """Raised when attempting to create a duplicate web automation."""
    
    def __init__(self, workflow_id: str, node_id: str):
        super().__init__(
            message=f"Web automation already exists for workflow {workflow_id}, node {node_id}",
            details={"workflow_id": workflow_id, "node_id": node_id}
        )


# Browser task exceptions
class BrowserTaskException(PremoveBaseException):
    """Base exception for browser task errors."""
    pass


class BrowserTaskFailedException(BrowserTaskException):
    """Raised when a browser task fails to complete successfully."""
    
    def __init__(self, task_goal: str, errors: list):
        super().__init__(
            message=f"Browser task failed: {task_goal}",
            details={"goal": task_goal, "errors": errors}
        )


class BrowserTaskTimeoutException(BrowserTaskException):
    """Raised when a browser task exceeds the timeout limit."""
    
    def __init__(self, task_goal: str, timeout: int):
        super().__init__(
            message=f"Browser task timed out after {timeout} seconds",
            details={"goal": task_goal, "timeout": timeout}
        )


# LLM API exceptions
class LLMException(PremoveBaseException):
    """Base exception for LLM-related errors."""
    pass


class LLMAPIException(LLMException):
    """Raised when LLM API call fails."""
    
    def __init__(self, provider: str, error: str):
        super().__init__(
            message=f"LLM API error from {provider}: {error}",
            details={"provider": provider, "error": error}
        )


class LLMTimeoutException(LLMException):
    """Raised when LLM API call times out."""
    
    def __init__(self, provider: str, timeout: int):
        super().__init__(
            message=f"LLM API timeout from {provider} after {timeout} seconds",
            details={"provider": provider, "timeout": timeout}
        )


# Database exceptions
class DatabaseException(PremoveBaseException):
    """Base exception for database errors."""
    pass


class DatabaseConnectionException(DatabaseException):
    """Raised when database connection fails."""
    pass


class DatabaseQueryException(DatabaseException):
    """Raised when a database query fails."""
    pass


# Configuration exceptions
class ConfigurationException(PremoveBaseException):
    """Raised when configuration is invalid or missing."""
    pass


# Authentication exceptions
class AuthenticationException(PremoveBaseException):
    """Base exception for authentication errors."""
    pass


class InvalidAPIKeyException(AuthenticationException):
    """Raised when API key is invalid."""
    
    def __init__(self):
        super().__init__(message="Invalid or missing API key")


class InvalidTokenException(AuthenticationException):
    """Raised when JWT token is invalid."""
    
    def __init__(self, reason: str = "Invalid token"):
        super().__init__(message=reason)


class TokenExpiredException(AuthenticationException):
    """Raised when JWT token has expired."""
    
    def __init__(self):
        super().__init__(message="Token has expired")
