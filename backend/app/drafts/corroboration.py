"""Exact cross-source corroboration, never semantic equivalence or arithmetic."""


def mergeable(existing, claim, identity=None):
    # Ambiguity, wording, labels, quantities and values must all survive.
    sources = {citation.source_id for citation in claim.citations}
    key = identity or (lambda value: value.model_dump(exclude={"citations"}))
    return (
        not claim.ambiguous
        and bool(sources)
        and not sources.intersection(c.source_id for c in existing.citations)
        and key(claim) == key(existing)
        and len(existing.citations) + len(claim.citations) <= 20
    )


def corroborate_claims(claims, *, identity=None):
    groups = []
    for claim in claims:
        for existing in groups:
            if mergeable(existing, claim, identity):
                existing.citations.extend(claim.model_copy(deep=True).citations)
                break
        else:
            groups.append(claim.model_copy(deep=True))
    return groups


def corroborate_typed(category, claims):
    """Read-only value projection; never replace saved wording or references.

    Summary labels allow case/spacing differences and a closed set of inclusive
    total aliases. Qualifying wording must still agree; a refundable deposit
    cannot merge with a non-refundable deposit. Original labels remain saved.
    Uncited authored rows and ambiguous/same-source repetitions cannot merge.
    """

    def identity(claim):
        value = claim.model_dump(exclude={"citations"})
        if category == "amounts" and claim.kind in {
            "rental_total",
            "deposit",
            "total_payable",
        }:
            label = " ".join(claim.label.casefold().split())
            if claim.kind == "total_payable" and label in {
                "total",
                "total payable",
                "inclusive total",
                "total payable (inclusive)",
            }:
                label = "total payable"
            value["label"] = label
        return value

    return corroborate_claims(claims, identity=identity)


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
