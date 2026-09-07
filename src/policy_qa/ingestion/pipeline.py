"""Create the search index and ingest the transformed policy records."""

from __future__ import annotations

import logging

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

from ..config import Settings
from ..utils.logging_setup import log_event
from ..schemas import PolicyRecord
from ..search.embeddings import EmbeddingService
from ..search.index_schema import create_or_update_index
from .catalog_download import download_catalog
from .catalog_transform import transform_catalog

logger = logging.getLogger(__name__)

MIN_RECORDS = 500


class IngestionError(RuntimeError):
    pass


def run_ingestion(settings: Settings) -> int:
    """Download -> transform -> embed -> upload. Returns number of docs ingested."""
    catalog = download_catalog()
    records = transform_catalog(catalog)
    log_event(logger, "catalog transformed", records=len(records))
    if len(records) < MIN_RECORDS:
        raise IngestionError(
            f"Only {len(records)} records after transformation; catalog sanity check requires >= {MIN_RECORDS}."
        )

    create_or_update_index(settings)

    embeddings = EmbeddingService(settings)
    texts = [f"{r.control_id} {r.title}\n{r.description}" for r in records]
    vectors = embeddings.embed(texts)

    client = SearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.search_index_name,
        credential=AzureKeyCredential(settings.search_api_key),
    )
    uploaded = 0
    batch_size = 200
    for i in range(0, len(records), batch_size):
        batch = [
            {**record.model_dump(), "content_vector": vector}
            for record, vector in zip(records[i : i + batch_size], vectors[i : i + batch_size])
        ]
        results = client.upload_documents(documents=batch)
        failed = [r for r in results if not r.succeeded]
        if failed:
            raise IngestionError(
                f"{len(failed)} documents failed to upload in batch starting at {i}: "
                f"{failed[0].error_message}"
            )
        uploaded += len(batch)
        log_event(logger, "batch uploaded", start=i, uploaded=uploaded)

    log_event(logger, "ingestion complete", total=uploaded, index=settings.search_index_name)
    return uploaded


def load_records() -> list[PolicyRecord]:
    """Convenience for tests and offline inspection."""
    return transform_catalog(download_catalog())
