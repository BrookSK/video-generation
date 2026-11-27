"""Keep the Blackwell worker on the tested FlashAttention backend."""

from xformers.ops.fmha.dispatch import _set_use_fa3

_set_use_fa3(False)
