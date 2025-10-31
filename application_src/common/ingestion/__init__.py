"""
Document Ingestion Module for GenAI-in-a-Box.

This module provides functionality for ingesting documents from S3,
processing them, and storing them in vector databases using LangChain.
"""

from .ingestion import DocumentIngestion

__all__ = ["DocumentIngestion"]
