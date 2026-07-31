from .models import Taxonomy, TaxonomyNode

__all__ = ["Taxonomy", "TaxonomyNode", "TaxonomyResolver"]


def __getattr__(name):
    if name == "TaxonomyResolver":
        from .resolver import TaxonomyResolver

        return TaxonomyResolver
    raise AttributeError(name)
