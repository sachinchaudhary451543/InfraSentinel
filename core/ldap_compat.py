"""
Compatibility shim for LDAP operations.

Tries to import the native `ldap` (python-ldap). If unavailable, falls back to
`ldap3` and provides a minimal compatible interface used by the project's
`domain_discovery.py` (initialize, filter.escape_filter_chars, constants,
and simple search/bind/unbind wrappers).
"""
import logging
from typing import List, Tuple, Dict

logger = logging.getLogger(__name__)

try:
    import ldap  # type: ignore
    # If native ldap is present, expose it directly
    from ldap import filter as filter
    # Re-export commonly used symbols so callers of this shim can use a
    # consistent API regardless of backend.
    initialize = ldap.initialize
    OPT_REFERRALS = getattr(ldap, 'OPT_REFERRALS', None)
    SCOPE_SUBTREE = getattr(ldap, 'SCOPE_SUBTREE', None)
except Exception:
    # Fallback to ldap3
    try:
        from ldap3 import Server, Connection, SUBTREE
        from ldap3.utils.conv import escape_filter_chars as _escape_filter_chars
    except Exception as e:
        raise ImportError(
            "Neither python-ldap nor ldap3 is available. Please install one: `pip install python-ldap` or `pip install ldap3`"
        ) from e

    # Provide minimal constants used by domain_discovery
    OPT_REFERRALS = None
    SCOPE_SUBTREE = SUBTREE

    class _FilterModule:
        @staticmethod
        def escape_filter_chars(s: str) -> str:
            return _escape_filter_chars(s)

    filter = _FilterModule()

    class _ConnectionWrapper:
        def __init__(self, server_uri: str):
            # ldap3 Server accepts host/uri
            self.server = Server(server_uri)
            self.conn = Connection(self.server, auto_bind=False)

        def set_option(self, *args, **kwargs):
            # No-op for ldap3 fallback
            return None

        def simple_bind_s(self):
            # ldap.simple_bind_s() with no args -> anonymous bind
            try:
                bound = self.conn.bind()
                if not bound:
                    raise Exception(f"ldap3 bind failed: {self.conn.result}")
                return True
            except Exception as e:
                raise

        def search_s(self, base_dn: str, scope, filterstr: str) -> List[Tuple[str, Dict[bytes, List[bytes]]]]:
            # Perform a search and return results in the form [(dn, {b'attr':[b'val']})]
            try:
                self.conn.search(search_base=base_dn, search_filter=filterstr, search_scope=SUBTREE, attributes='*')
                results = []
                for entry in self.conn.entries:
                    dn = entry.entry_dn
                    attrs = {}
                    for attr_name, attr_value in entry.entry_attributes_as_dict.items():
                        # Ensure values are bytes lists to mimic python-ldap
                        values = attr_value if isinstance(attr_value, list) else [attr_value]
                        byte_values = []
                        for v in values:
                            try:
                                byte_values.append(v.encode() if isinstance(v, str) else bytes(v))
                            except Exception:
                                # fallback str->bytes
                                byte_values.append(str(v).encode())
                        attrs[attr_name.encode()] = byte_values
                    results.append((dn, attrs))
                return results
            except Exception as e:
                logger.error(f"ldap3 search error: {e}")
                raise

        def unbind_s(self):
            try:
                self.conn.unbind()
            except Exception:
                pass

    def initialize(server_uri: str):
        return _ConnectionWrapper(server_uri)

    # expose a simple module-like interface
    ldap = None


# Export a stable public API for static analysis tools and callers
__all__ = [
    'initialize',
    'OPT_REFERRALS',
    'SCOPE_SUBTREE',
    'filter'
]
