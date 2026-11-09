"""Exact cross-source corroboration, never semantic equivalence or arithmetic."""


def mergeable(existing, claim):
    # Ambiguity, wording, labels, quantities and values must all survive.
    sources = {citation.source_id for citation in claim.citations}
    return (
        not claim.ambiguous
        and bool(sources)
        and not sources.intersection(c.source_id for c in existing.citations)
        and claim.model_dump(exclude={"citations"})
        == existing.model_dump(exclude={"citations"})
        and len(existing.citations) + len(claim.citations) <= 20
    )


def corroborate_claims(claims):
    groups = []
    for claim in claims:
        for existing in groups:
            if mergeable(existing, claim):
                existing.citations.extend(claim.model_copy(deep=True).citations)
                break
        else:
            groups.append(claim.model_copy(deep=True))
    return groups


def corroborate_extraction(extraction):
    return type(extraction)(
        **{
            category: corroborate_claims(getattr(extraction, category))
            for category in type(extraction).model_fields
        }
    )


def corroborate_review(content):
    """Only called when explicitly saving a new immutable review version."""
    result = content.model_copy(deep=True)
    for category in type(content.extraction).model_fields:
        entries = []
        for entry in getattr(content.extraction, category):
            match = next(
                (
                    existing
                    for existing in entries
                    if entry.origin == existing.origin == "source_supported"
                    and mergeable(existing.claim, entry.claim)
                ),
                None,
            )
            if match is not None:
                match.claim.citations.extend(
                    entry.claim.model_copy(deep=True).citations
                )
            else:
                # Preserve order, customer-entered provenance and correction reasons.
                entries.append(entry.model_copy(deep=True))
        setattr(result.extraction, category, entries)
    return result
