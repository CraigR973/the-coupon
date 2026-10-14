"""The payments service: the second Railway process ADR 0009 option B puts the Monzo token in.

Batch 207 gives it only a boot and a health pair; Batch 208 adds the Monzo reading. It is
built from this repository and shares the API's models, but never imports ``src.config`` or
``src.main``: those demand the API's own secrets in production and start its scheduler, and
this process holds none of them.
"""
